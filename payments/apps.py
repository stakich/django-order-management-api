import stripe
from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "payments"

    def ready(self):
        from . import checks  # noqa: F401

        stripe.default_http_client = stripe.RequestsClient(timeout=(3, 8))
        stripe.max_network_retries = 1
