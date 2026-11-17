
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from orders.models import Order
from payments.models import Payment


class CheckoutThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="checkout_throttle_user",
            password="testpassword123",
        )
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    @patch(
        "payments.views.PaymentService.create_checkout_session",
        return_value="https://checkout.stripe.com/test",
    )
    def test_checkout_is_throttled_after_ten_requests(self, mock_checkout):
        url = "/api/v1/orders/1/checkout/"

        for _ in range(10):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 200)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(mock_checkout.call_count, 10)

    @patch(
        "payments.views.PaymentService.create_checkout_session",
        return_value="https://checkout.stripe.com/test",
    )
    def test_throttle_is_per_user(self, mock_checkout):
        url = "/api/v1/orders/1/checkout/"

        for _ in range(10):
            self.client.post(url)

        other_user = get_user_model().objects.create_user(
            username="other_checkout_user",
            password="testpassword123",
        )
        self.client.force_authenticate(user=other_user)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_checkout.call_count, 11)


class PaymentAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="payment_admin",
            email="admin@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        order = Order.objects.create(user=self.user)
        self.payment = Payment.objects.create(
            order=order,
            amount=Decimal("20.00"),
        )

    def test_admin_can_view_payments(self):
        list_url = reverse("admin:payments_payment_changelist")
        detail_url = reverse(
            "admin:payments_payment_change",
            args=[self.payment.pk],
        )

        self.assertEqual(self.client.get(list_url).status_code, 200)
        self.assertEqual(self.client.get(detail_url).status_code, 200)

    def test_admin_cannot_modify_payments(self):
        add_url = reverse("admin:payments_payment_add")
        change_url = reverse(
            "admin:payments_payment_change",
            args=[self.payment.pk],
        )
        delete_url = reverse(
            "admin:payments_payment_delete",
            args=[self.payment.pk],
        )

        self.assertEqual(self.client.get(add_url).status_code, 403)
        self.assertEqual(
            self.client.post(
                change_url,
                {"status": Payment.Status.SUCCEEDED},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(delete_url).status_code, 403)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
