
from unittest.mock import patch

import stripe
from django.apps import apps
from django.core.checks import run_checks
from django.test import SimpleTestCase, override_settings

from payments.checks import check_stripe_credentials


class StripeConfigurationTests(SimpleTestCase):
    def test_stripe_http_configuration(self):
        with (
            patch("payments.apps.stripe.RequestsClient") as client,
            patch.object(stripe, "default_http_client", None),
            patch.object(stripe, "max_network_retries", 2),
        ):
            apps.get_app_config("payments").ready()

            client.assert_called_once_with(timeout=(3, 8))
            self.assertIs(
                stripe.default_http_client,
                client.return_value,
            )
            self.assertEqual(stripe.max_network_retries, 1)

    @override_settings(
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_missing_stripe_credentials_produce_warnings(self):
        warnings = check_stripe_credentials(None)

        self.assertEqual(
            {warning.id for warning in warnings},
            {"payments.W001", "payments.W002"},
        )

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_example",
        STRIPE_WEBHOOK_SECRET="whsec_example",
    )
    def test_configured_credentials_produce_no_warnings(self):
        self.assertEqual(check_stripe_credentials(None), [])

    @override_settings(
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
    )
    def test_checks_run_only_during_deployment_checks(self):
        normal = {
            warning.id
            for warning in run_checks()
            if warning.id.startswith("payments.")
        }

        deployment = {
            warning.id
            for warning in run_checks(include_deployment_checks=True)
            if warning.id.startswith("payments.")
        }

        self.assertEqual(normal, set())
        self.assertEqual(
            deployment,
            {"payments.W001", "payments.W002"},
        )
