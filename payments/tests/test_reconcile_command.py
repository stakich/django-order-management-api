from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from orders.models import Order
from payments.models import Payment


class ReconcilePaymentsCommandTests(SimpleTestCase):
    @patch(
        "payments.management.commands.reconcile_payments.PaymentService.reconcile_known_checkout"
    )
    @patch("payments.management.commands.reconcile_payments.Payment.objects.filter")
    def test_reconciles_eligible_payments(self, mock_filter, mock_reconcile):
        queryset = mock_filter.return_value.order_by.return_value
        queryset.values_list.return_value.iterator.return_value = iter([10, 11])

        output = StringIO()

        call_command("reconcile_payments", stdout=output)

        self.assertEqual(mock_reconcile.call_count, 2)
        mock_reconcile.assert_any_call(10)
        mock_reconcile.assert_any_call(11)

        self.assertIn("checked=2, failed=0", output.getvalue())

    @patch(
        "payments.management.commands.reconcile_payments.PaymentService.reconcile_known_checkout"
    )
    @patch("payments.management.commands.reconcile_payments.Payment.objects.filter")
    def test_continues_after_payment_failure(self, mock_filter, mock_reconcile):
        from payments.exceptions import PaymentProviderError

        queryset = mock_filter.return_value.order_by.return_value
        queryset.values_list.return_value.iterator.return_value = iter([10, 11])

        mock_reconcile.side_effect = [
            PaymentProviderError("Stripe unavailable"),
            None,
        ]

        output = StringIO()

        with self.assertLogs(
                "payments.management.commands.reconcile_payments",
                level="ERROR",
        ):
            call_command("reconcile_payments", stdout=output)

        self.assertEqual(mock_reconcile.call_count, 2)
        mock_reconcile.assert_any_call(10)
        mock_reconcile.assert_any_call(11)
        self.assertIn("checked=1, failed=1", output.getvalue())


class ReconcilePaymentsFilteringTests(TestCase):
    @patch(
        "payments.management.commands.reconcile_payments.PaymentService.reconcile_known_checkout"
    )
    def test_selects_only_old_pending_ready_payments(self, mock_reconcile):
        user = get_user_model().objects.create_user(
            username="reconcile_tester",
            password="test-password",
        )

        def create_payment(status, checkout_status, session_id, age_minutes):
            order = Order.objects.create(user=user)

            payment = Payment.objects.create(
                order=order,
                amount=Decimal("30.00"),
                status=status,
                checkout_status=checkout_status,
                stripe_session_id=session_id,
            )

            Payment.objects.filter(pk=payment.pk).update(
                updated_at=timezone.now() - timedelta(minutes=age_minutes)
            )

            return payment

        eligible = create_payment(
            Payment.Status.PENDING,
            Payment.CheckoutStatus.READY,
            "cs_eligible",
            30,
        )

        create_payment(
            Payment.Status.PENDING,
            Payment.CheckoutStatus.READY,
            "cs_recent",
            5,
        )

        create_payment(
            Payment.Status.FAILED,
            Payment.CheckoutStatus.EXPIRED,
            "cs_failed",
            30,
        )

        create_payment(
            Payment.Status.PENDING,
            Payment.CheckoutStatus.CREATING,
            None,
            30,
        )

        output = StringIO()

        call_command("reconcile_payments", stdout=output)

        mock_reconcile.assert_called_once_with(eligible.id)
        self.assertIn("checked=1, failed=0", output.getvalue())

@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class ReconcileMissingWebhookTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="missing_webhook_user",
            password="testpassword123",
        )

        self.order = Order.objects.create(user=user)

        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("100.00"),
            currency="EUR",
            status=Payment.Status.PENDING,
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_missing_webhook",
        )

        Payment.objects.filter(pk=self.payment.pk).update(
            updated_at=timezone.now() - timedelta(minutes=20)
        )

    def make_session(self, payment_status):
        return stripe.checkout.Session.construct_from(
            {
                "id": "cs_test_missing_webhook",
                "mode": "payment",
                "status": "complete",
                "payment_status": payment_status,
                "amount_total": 10000,
                "currency": "eur",
                "metadata": {
                    "order_id": str(self.order.pk),
                    "payment_id": str(self.payment.pk),
                },
            },
            "sk_test_dummy",
        )

    @patch("payments.services.stripe.checkout.Session.retrieve")
    def test_recovers_successful_payment_without_webhook(self, retrieve):
        retrieve.return_value = self.make_session("paid")

        call_command("reconcile_payments", stdout=StringIO())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.SUCCEEDED,
        )
        self.assertEqual(self.order.status, Order.Status.PAID)
        retrieve.assert_called_once_with("cs_test_missing_webhook")

    @patch("payments.services.stripe.checkout.Session.retrieve")
    def test_async_payment_remains_pending(self, retrieve):
        retrieve.return_value = self.make_session("unpaid")

        call_command("reconcile_payments", stdout=StringIO())

        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(
            self.payment.status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            self.payment.checkout_status,
            Payment.CheckoutStatus.READY,
        )
        self.assertEqual(self.order.status, Order.Status.PENDING)
