import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from orders.models import Order
from orders.services import OrderService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Cancel expired orders and restore reserved stock."

    def handle(self, *args, **options):
        cutoff = timezone.now()

        order_ids = (
            Order.objects.filter(
                status=Order.Status.PENDING,
                expires_at__lte=cutoff,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )

        expired = 0
        skipped = 0
        failed = 0

        for order_id in order_ids.iterator(chunk_size=200):
            try:
                if OrderService.expire_order(order_id):
                    expired += 1
                else:
                    skipped += 1

            except Exception:
                failed += 1
                logger.exception(
                    "Order expiration failed for order %s",
                    order_id,
                )

        self.stdout.write(
            f"Order expiration completed: expired={expired}, skipped={skipped}, failed={failed}"
        )

        if failed:
            raise CommandError(f"Order expiration failed for {failed} order(s)")
