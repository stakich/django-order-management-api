
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_login_is_throttled_after_five_requests(self):
        url = reverse("token_obtain_pair")

        for _ in range(5):
            response = self.client.post(
                url,
                {"username": "unknown", "password": "wrong"},
                format="json",
            )
            self.assertEqual(response.status_code, 401)

        response = self.client.post(
            url,
            {"username": "unknown", "password": "wrong"},
            format="json",
        )

        self.assertEqual(response.status_code, 429)
