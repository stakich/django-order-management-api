
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import Order
from orders.services import OrderService
from payments.models import Payment
from products.models import Category, Product


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class LostSessionRecoveryTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="recovery_customer",
            password="testpassword123",
        )

        category = Category.objects.create(
            name="Recovery",
            slug="recovery",
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="RECOVERY-001",
            price=Decimal("1000.00"),
            stock=5,
            category=category,
        )

        self.order = OrderService.create_order(
            user=user,
            items=[{"product": self.product.id, "quantity": 2}],
        )

        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("2000.00"),
            checkout_status=Payment.CheckoutStatus.CREATING,
            checkout_claimed_at=timezone.now() - timedelta(minutes=11),
        )

    def make_session(self, status, payment_status):
        return stripe.checkout.Session.construct_from(
            {
                "id": "cs_test_recovered",
                "mode": "payment",
                "status": status,
                "payment_status": payment_status,
                "amount_total": 200000,
                "currency": "eur",
                "metadata": {
                    "order_id": str(self.order.id),
                    "payment_id": str(self.payment.id),
                },
            },
            "sk_test_dummy",
        )

    @patch("payments.services.stripe.checkout.Session.retrieve")
    @patch("payments.services.stripe.checkout.Session.create")
    def test_recovers_open_session(self, create, retrieve):
        create.return_value = SimpleNamespace(id="cs_test_recovered")
        retrieve.return_value = self.make_session("open", "unpaid")

        result = OrderService.expire_order(self.order.id)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(
            self.payment.checkout_status,
            Payment.CheckoutStatus.READY,
        )
        self.assertEqual(self.payment.stripe_session_id, "cs_test_recovered")
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)

        self.assertEqual(
            create.call_args.kwargs["idempotency_key"],
            f"checkout-payment-{self.payment.id}",
        )

    @patch("payments.services.stripe.checkout.Session.retrieve")
    @patch("payments.services.stripe.checkout.Session.create")
    def test_recovered_payment_was_successful(self, create, retrieve):
        create.return_value = SimpleNamespace(id="cs_test_recovered")
        retrieve.return_value = self.make_session("complete", "paid")

        result = OrderService.expire_order(self.order.id)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.product.stock, 3)

    @patch("payments.services.stripe.checkout.Session.create")
    def test_does_not_retry_after_23_hour_window(self, create):
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(hours=24)
        )

        result = OrderService.expire_order(self.order.id)

        self.assertFalse(result)
        create.assert_not_called()

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)

