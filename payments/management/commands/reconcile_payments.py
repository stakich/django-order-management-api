
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.exceptions import PaymentNotAllowedError, PaymentProviderError
from payments.models import Payment
from payments.services import PaymentService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcile pending Stripe payments with known checkout sessions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=15,
            help="Minimum age of payments to reconcile (default: 15).",
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]

        if minutes < 1:
            raise ValueError("--minutes must be a positive integer")

        cutoff = timezone.now() - timedelta(minutes=minutes)

        payment_ids = (
            Payment.objects.filter(
                status=Payment.Status.PENDING,
                provider="STRIPE",
                checkout_status=Payment.CheckoutStatus.READY,
                updated_at__lte=cutoff,
                stripe_session_id__isnull=False,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )

        checked = 0
        failed = 0

        for payment_id in payment_ids.iterator():
            try:
                PaymentService.reconcile_known_checkout(payment_id)
                checked += 1
            except (PaymentNotAllowedError, PaymentProviderError, Payment.DoesNotExist):
                failed += 1
                logger.exception(
                    "Stripe reconciliation failed for payment %s",
                    payment_id,
                )

        self.stdout.write(
            f"Reconciliation completed: checked={checked}, failed={failed}"
        )
