
import logging
from datetime import timedelta
from itertools import islice

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
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
            help="Minimum payment age and reconciliation interval.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum payments to process per execution.",
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        limit = options["limit"]

        if minutes < 1 or limit < 1:
            raise CommandError("--minutes and --limit must be positive")

        cutoff = timezone.now() - timedelta(minutes=minutes)

        eligible = (
            Q(last_reconciled_at__isnull=True)
            | Q(last_reconciled_at__lte=cutoff)
        )

        payment_ids = (
            Payment.objects.filter(
                eligible,
                status=Payment.Status.PENDING,
                provider="STRIPE",
                checkout_status=Payment.CheckoutStatus.READY,
                stripe_session_id__isnull=False,
                updated_at__lte=cutoff,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )

        checked = 0
        failed = 0

        for payment_id in islice(payment_ids.iterator(), limit):
            now = timezone.now()
            retry_cutoff = now - timedelta(minutes=minutes)

            # Atomically claim this payment before contacting Stripe.
            claimed = Payment.objects.filter(
                Q(last_reconciled_at__isnull=True)
                | Q(last_reconciled_at__lte=retry_cutoff),
                pk=payment_id,
                status=Payment.Status.PENDING,
                provider="STRIPE",
                checkout_status=Payment.CheckoutStatus.READY,
                stripe_session_id__isnull=False,
                updated_at__lte=retry_cutoff,
            ).update(last_reconciled_at=now)

            if not claimed:
                continue

            try:
                PaymentService.reconcile_known_checkout(payment_id)
                checked += 1

            except (
                PaymentNotAllowedError,
                PaymentProviderError,
                Payment.DoesNotExist,
            ):
                failed += 1
                logger.exception(
                    "Stripe reconciliation failed for payment %s",
                    payment_id,
                )

        self.stdout.write(
            f"Reconciliation completed: checked={checked}, failed={failed}"
        )
