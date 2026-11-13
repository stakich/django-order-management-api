
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from payments.exceptions import PaymentProviderError
from payments.models import Payment
from payments.services import PaymentService


class CheckoutExpirationTests(SimpleTestCase):
    @patch("payments.services.PaymentService.handle_expired_checkout")
    @patch("payments.services.stripe.checkout.Session.expire")
    @patch("payments.services.PaymentService.reconcile_known_checkout")
    def test_open_checkout_is_expired(
        self, reconcile, stripe_expire, handle_expired
    ):
        reconcile.return_value = Mock(
            status=Payment.Status.PENDING,
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_123",
        )

        session = {
            "id": "cs_test_123",
            "status": "expired",
            "payment_status": "unpaid",
        }
        stripe_expire.return_value = session

        handle_expired.return_value = Mock(
            status=Payment.Status.PENDING,
            checkout_status=Payment.CheckoutStatus.EXPIRED,
        )

        result = PaymentService.ensure_checkout_expired(1)

        self.assertTrue(result)
        stripe_expire.assert_called_once_with("cs_test_123")
        handle_expired.assert_called_once_with(session)

    @patch("payments.services.stripe.checkout.Session.expire")
    @patch("payments.services.PaymentService.reconcile_known_checkout")
    def test_paid_checkout_is_not_expired(self, reconcile, stripe_expire):
        reconcile.return_value = Mock(
            status=Payment.Status.SUCCEEDED,
        )

        result = PaymentService.ensure_checkout_expired(1)

        self.assertFalse(result)
        stripe_expire.assert_not_called()

    @patch("payments.services.stripe.checkout.Session.expire")
    @patch("payments.services.PaymentService.reconcile_known_checkout")
    def test_stripe_unavailable_keeps_reservation(
        self, reconcile, stripe_expire
    ):
        reconcile.side_effect = PaymentProviderError(
            "Stripe unavailable"
        )

        result = PaymentService.ensure_checkout_expired(1)

        self.assertFalse(result)
        stripe_expire.assert_not_called()
