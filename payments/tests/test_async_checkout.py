
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Order
from orders.services import OrderService
from payments.models import Payment
from payments.services import PaymentService
from products.models import Category, Product


class StripeSession(dict):
    def to_dict(self):
        return dict(self)


class AsyncCheckoutTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="async_customer",
            password="testpassword123",
        )

        category = Category.objects.create(
            name="Electronics",
            slug="async-electronics",
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="ASYNC-001",
            price=Decimal("1000.00"),
            stock=5,
            category=category,
        )

        self.order = OrderService.create_order(
            user=user,
            items=[{"product": self.product.pk, "quantity": 2}],
        )

        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("2000.00"),
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_async",
        )

    def make_session(self):
        return StripeSession({
            "id": "cs_test_async",
            "mode": "payment",
            "status": "complete",
            "payment_status": "unpaid",
            "amount_total": 200000,
            "currency": "eur",
            "metadata": {
                "order_id": str(self.order.pk),
                "payment_id": str(self.payment.pk),
            },
        })

    def test_async_failure_marks_payment_failed(self):
        PaymentService.handle_failed_async_checkout(
            self.make_session()
        )

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.FAILED,
        )
        self.assertEqual(
            self.order.status,
            Order.Status.PENDING,
        )
        self.assertEqual(self.product.stock, 3)

    def test_duplicate_async_failure_is_idempotent(self):
        session = self.make_session()

        PaymentService.handle_failed_async_checkout(session)
        PaymentService.handle_failed_async_checkout(session)

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.FAILED,
        )

    def test_invalid_amount_is_rejected(self):
        from payments.exceptions import PaymentNotAllowedError

        session = self.make_session()
        session["amount_total"] = 100

        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_failed_async_checkout(session)

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )

    @patch("payments.views.stripe.Webhook.construct_event")
    def test_async_failure_webhook(self, construct_event):
        construct_event.return_value = {
            "type": "checkout.session.async_payment_failed",
            "data": {"object": self.make_session()},
        }

        response = self.client.post(
            "/api/v1/payments/stripe/webhook/",
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_signature",
        )

        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.FAILED,
        )
