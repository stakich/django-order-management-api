
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from rest_framework import status
from rest_framework.test import APITestCase

from orders.models import Order


User = get_user_model()


class OrderAPIRetryTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="retry_customer",
            password="testpassword123"
        )

        self.client.force_authenticate(user=self.user)
        self.url = "/api/v1/orders/"

    @patch("orders.utils.transaction_retry.time.sleep")
    @patch("orders.views.OrderService.create_order")
    def test_order_creation_retries_after_serialization_failure(
        self,
        mock_create_order,
        mock_sleep
    ):
        # 1. Simulate PostgreSQL serialization failure
        postgres_error = Exception("Serialization failure")
        postgres_error.sqlstate = "40001"

        django_error = OperationalError(
            "Could not serialize access due to concurrent update"
        )
        django_error.__cause__ = postgres_error

        # 2. Create an order to return on the successful attempt
        order = Order.objects.create(user=self.user)

        # 3. First attempt fails, second succeeds
        mock_create_order.side_effect = [
            django_error,
            order
        ]

        # 4. Send the API request
        response = self.client.post(
            self.url,
            data={
                "items": [
                    {
                        "product": 1,
                        "quantity": 1
                    }
                ]
            },
            format="json"
        )

        # 5. Verify API response
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(response.data["id"], order.id)
        self.assertEqual(response.data["status"], Order.Status.PENDING)

        # 6. Verify retries
        self.assertEqual(mock_create_order.call_count, 2)

        # 7. Verify arguments passed to the service
        mock_create_order.assert_called_with(
            user=self.user,
            items=[
                {
                    "product": 1,
                    "quantity": 1
                }
            ]
        )

        # 8. Verify delay between attempts
        mock_sleep.assert_called_once_with(0.1)
