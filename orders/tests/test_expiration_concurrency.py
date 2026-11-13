from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from orders.models import Order
from orders.services import OrderService
from payments.models import Payment
from payments.services import PaymentService
from products.models import Category, Product


class StripeSession(dict):
    def to_dict(self):
        return dict(self)


class OrderExpirationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL")

        user = get_user_model().objects.create_user(
            username="expiration_customer",
            password="testpassword123",
        )

        category = Category.objects.create(
            name="Electronics",
            slug="electronics",
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="EXP-CONCURRENT-001",
            price=Decimal("1000.00"),
            stock=5,
            category=category,
            is_active=True,
        )

        self.order = OrderService.create_order(
            user=user,
            items=[{"product": self.product.pk, "quantity": 2}],
        )

        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("2000.00"),
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_race",
        )

    def test_webhook_wins_before_expiration_finalization(self):
        webhook_updated = Event()
        expiration_checked = Event()

        session = StripeSession({
            "id": "cs_test_race",
            "mode": "payment",
            "payment_status": "paid",
            "amount_total": 200000,
            "currency": "eur",
            "metadata": {
                "order_id": str(self.order.pk),
                "payment_id": str(self.payment.pk),
            },
        })

        def webhook():
            close_old_connections()
            try:
                with transaction.atomic():
                    PaymentService.handle_successful_checkout(session)

                    # Keep the Order lock until expiration
                    # has reached its Stripe verification.
                    webhook_updated.set()

                    if not expiration_checked.wait(timeout=10):
                        raise TimeoutError("Expiration did not reach verification")
            finally:
                close_old_connections()

        def fake_stripe_check(payment_id):
            self.assertEqual(payment_id, self.payment.pk)
            expiration_checked.set()
            return True

        def expire():
            close_old_connections()
            try:
                if not webhook_updated.wait(timeout=10):
                    raise TimeoutError("Webhook did not update Order")

                return OrderService.expire_order(self.order.pk)
            finally:
                close_old_connections()

        with patch(
            "orders.services.PaymentService.ensure_checkout_expired",
            side_effect=fake_stripe_check,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                webhook_future = executor.submit(webhook)
                expiration_future = executor.submit(expire)

                webhook_future.result(timeout=15)
                result = expiration_future.result(timeout=15)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.product.stock, 3)

    def test_payment_succeeds_during_stripe_verification(self):
        verification_started = Event()
        webhook_completed = Event()

        session = StripeSession({
            "id": "cs_test_race",
            "mode": "payment",
            "payment_status": "paid",
            "amount_total": 200000,
            "currency": "eur",
            "metadata": {
                "order_id": str(self.order.pk),
                "payment_id": str(self.payment.pk),
            },
        })

        def fake_stripe_retrieve(session_id):
            self.assertEqual(session_id, "cs_test_race")

            verification_started.set()

            if not webhook_completed.wait(timeout=10):
                raise TimeoutError("Webhook did not complete")

            return session

        def expire():
            close_old_connections()
            try:
                return OrderService.expire_order(self.order.pk)
            finally:
                close_old_connections()

        def webhook():
            close_old_connections()
            try:
                if not verification_started.wait(timeout=10):
                    raise TimeoutError("Stripe verification did not start")

                PaymentService.handle_successful_checkout(session)
            finally:
                webhook_completed.set()
                close_old_connections()

        with (
            patch(
                "payments.services.stripe.checkout.Session.retrieve",
                side_effect=fake_stripe_retrieve,
            ),
            patch(
                "payments.services.stripe.checkout.Session.expire",
            ) as stripe_expire,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                expiration_future = executor.submit(expire)
                webhook_future = executor.submit(webhook)

                result = expiration_future.result(timeout=15)
                webhook_future.result(timeout=15)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.product.stock, 3)

        stripe_expire.assert_not_called()
