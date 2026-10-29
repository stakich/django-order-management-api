from django.db import models

# Create your models here.

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    class CheckoutStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        CREATING = "CREATING", "Creating"
        READY = "READY", "Ready"
        EXPIRED = "EXPIRED", "Expired"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    status = models.CharField(max_length=10, default=Status.PENDING, choices=Status.choices)
    provider = models.CharField(max_length=30, default="STRIPE")
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    checkout_status = models.CharField(max_length=30, default=CheckoutStatus.NOT_STARTED, choices=CheckoutStatus.choices)
    checkout_claimed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(
                    status__in=["PENDING", "SUCCEEDED"]
                ),
                name="unique_active_or_succeeded_payment_per_order"
            )
        ]