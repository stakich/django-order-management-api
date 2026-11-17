from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import override_settings
from rest_framework.test import APITestCase

from orders.models import Order
from payments.models import Payment


class StripeSession(dict):
    def to_dict(self):
        return dict(self)


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
class StripeWebhookResponseTests(APITestCase):
    url = "/api/v1/payments/stripe/webhook/"

    def setUp(self):
        user = get_user_model().objects.create_user(
            username="webhook_response_user",
            password="testpassword123",
        )

        self.order = Order.objects.create(user=user)

        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("19.99"),
            currency="EUR",
            status=Payment.Status.PENDING,
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_webhook",
        )

    def make_event(self, event_type="checkout.session.completed"):
        session = StripeSession(
            {
                "id": "cs_test_webhook",
                "mode": "payment",
                "status": "complete",
                "payment_status": "paid",
                "amount_total": 1999,
                "currency": "eur",
                "payment_intent": "pi_test_webhook",
                "metadata": {
                    "order_id": str(self.order.id),
                    "payment_id": str(self.payment.id),
                },
            }
        )

        return {
            "id": "evt_test_webhook",
            "type": event_type,
            "data": {"object": session},
        }

    def send_event(self, event):
        with patch(
            "payments.views.stripe.Webhook.construct_event",
            return_value=event,
        ):
            return self.client.post(
                self.url,
                data="{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test_signature",
            )

    def test_invalid_signature_returns_400(self):
        response = self.client.post(
            self.url,
            data="{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, 400)

    def test_unsupported_event_returns_200(self):
        event = self.make_event("customer.created")

        response = self.send_event(event)

        self.assertEqual(response.status_code, 200)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_missing_payment_id_returns_200(self):
        event = self.make_event()
        event["data"]["object"]["metadata"] = {
            "order_id": str(self.order.id),
        }

        with self.assertLogs("payments.views", level="WARNING"):
            response = self.send_event(event)

        self.assertEqual(response.status_code, 200)

    def test_invalid_payment_id_returns_200(self):
        event = self.make_event()
        event["data"]["object"]["metadata"]["payment_id"] = "invalid"

        with self.assertLogs("payments.views", level="CRITICAL"):
            response = self.send_event(event)

        self.assertEqual(response.status_code, 200)

    def test_unknown_payment_returns_200(self):
        event = self.make_event()
        event["data"]["object"]["metadata"]["payment_id"] = "999999"

        with self.assertLogs("payments.views", level="CRITICAL"):
            response = self.send_event(event)

        self.assertEqual(response.status_code, 200)

    def test_paid_cancelled_order_returns_200(self):
        self.order.status = Order.Status.CANCELLED
        self.order.save(update_fields=["status"])

        event = self.make_event()

        with self.assertLogs("payments.views", level="CRITICAL"):
            response = self.send_event(event)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_successful_payment_returns_200(self):
        event = self.make_event()

        response = self.send_event(event)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)

    def test_duplicate_webhook_is_idempotent(self):
        event = self.make_event()

        first = self.send_event(event)
        second = self.send_event(event)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(
            Payment.objects.filter(order=self.order).count(),
            1,
        )

    @patch(
        "payments.views.PaymentService.handle_successful_checkout",
        side_effect=OperationalError("Database unavailable"),
    )
    def test_database_error_returns_500(self, mock_handler):
        self.client.raise_request_exception = False

        event = self.make_event()
        response = self.send_event(event)

        self.assertEqual(response.status_code, 500)
        mock_handler.assert_called_once()
