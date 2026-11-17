from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def check_stripe_credentials(app_configs, **kwargs):
    warnings = []

    if not settings.STRIPE_SECRET_KEY:
        warnings.append(
            Warning(
                "STRIPE_SECRET_KEY is not configured.",
                id="payments.W001",
            )
        )

    if not settings.STRIPE_WEBHOOK_SECRET:
        warnings.append(
            Warning(
                "STRIPE_WEBHOOK_SECRET is not configured.",
                id="payments.W002",
            )
        )

    return warnings
