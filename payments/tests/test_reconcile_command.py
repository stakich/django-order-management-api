from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
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
