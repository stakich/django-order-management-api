from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Order
from payments.exceptions import PaymentNotAllowedError
from payments.models import Payment
from payments.services import PaymentService


class StripeSession(dict):
    """Minimal representation of the verified Checkout Session payload."""

    def to_dict(self):
        return dict(self)


class SuccessfulCheckoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="webhook_tester", password="test-password"
        )

    def setUp(self):
        self.order = Order.objects.create(user=self.user)
        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("19.99"),
            currency="EUR",
            checkout_status=Payment.CheckoutStatus.CREATING,
        )

    def session(self, **overrides):
        data = {
            "id": "cs_test_webhook_123",
            "mode": "payment",
            "payment_status": "paid",
            "amount_total": 1999,
            "currency": "eur",
            "metadata": {
                "order_id": str(self.order.id),
                "payment_id": str(self.payment.id),
            },
        }
        data.update(overrides)
        return StripeSession(data)

    def test_normal_successful_payment(self):
        self.payment.stripe_session_id = "cs_test_webhook_123"
        self.payment.checkout_status = Payment.CheckoutStatus.READY
        self.payment.save(update_fields=["stripe_session_id", "checkout_status"])

        PaymentService.handle_successful_checkout(self.session())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_early_webhook_saves_session_and_marks_paid(self):
        PaymentService.handle_successful_checkout(self.session())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.stripe_session_id, "cs_test_webhook_123")
        self.assertEqual(self.payment.checkout_status, Payment.CheckoutStatus.READY)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_save_stripe_session_after_early_webhook(self):
        from types import SimpleNamespace

        session = self.session()
        PaymentService.handle_successful_checkout(session)
        saved = PaymentService.save_stripe_session(self.payment, SimpleNamespace(id=session["id"]))
        self.assertEqual(saved.status, Payment.Status.SUCCEEDED)
        self.assertEqual(saved.stripe_session_id, session["id"])

    def test_duplicate_webhook_is_idempotent(self):
        session = self.session()
        PaymentService.handle_successful_checkout(session)
        PaymentService.handle_successful_checkout(session)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    def test_wrong_session_id_is_rejected(self):
        self.payment.stripe_session_id = "cs_test_original"
        self.payment.checkout_status = Payment.CheckoutStatus.READY
        self.payment.save(update_fields=["stripe_session_id", "checkout_status"])

        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_successful_checkout(self.session())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_wrong_amount_is_rejected(self):
        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_successful_checkout(self.session(amount_total=999))

        self.payment.refresh_from_db()
        self.assertIsNone(self.payment.stripe_session_id)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_wrong_order_metadata_is_rejected(self):
        metadata = {
            "payment_id": str(self.payment.id),
            "order_id": str(self.order.id + 1000),
        }
        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_successful_checkout(self.session(metadata=metadata))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_cancelled_order_is_not_marked_paid(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["status"])

        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_successful_checkout(self.session())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
