from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


class RegistrationThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_registration_is_throttled_after_three_requests(self):
        url = reverse("register")

        for _ in range(3):
            response = self.client.post(url, {}, format="json")
            self.assertEqual(response.status_code, 400)

        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, 429)
