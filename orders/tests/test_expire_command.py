
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from orders.models import Order
from orders.services import OrderService
from payments.models import Payment
from products.models import Category, Product


class ExpireOrdersCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="expiration_command_user",
            password="testpassword123",
        )

        category = Category.objects.create(
            name="Electronics",
            slug="command-electronics",
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="CMD-EXP-001",
            price=Decimal("1000.00"),
            stock=5,
            category=category,
            is_active=True,
        )

        self.order = OrderService.create_order(
            user=self.user,
            items=[
                {"product": self.product.pk, "quantity": 2},
            ],
        )

    def test_expired_order_is_cancelled(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        output = StringIO()
        call_command("expire_orders", stdout=output)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)
        self.assertIn("expired=1", output.getvalue())

    def test_active_order_is_not_cancelled(self):
        output = StringIO()
        call_command("expire_orders", stdout=output)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)
        self.assertIn("expired=0", output.getvalue())

    def test_pending_payment_prevents_expiration(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        Payment.objects.create(
            order=self.order,
            amount=Decimal("2000.00"),
            checkout_status=Payment.CheckoutStatus.CREATING,
            checkout_claimed_at=timezone.now(),
        )

        output = StringIO()
        call_command("expire_orders", stdout=output)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)
        self.assertIn("skipped=1", output.getvalue())

    def test_repeated_execution_does_not_restore_stock_twice(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        call_command("expire_orders", stdout=StringIO())
        call_command("expire_orders", stdout=StringIO())

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, 5)

    @patch(
        "orders.management.commands.expire_orders."
        "OrderService.expire_order"
    )
    def test_command_continues_after_failure(self, mock_expire):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        second_order = OrderService.create_order(
            user=self.user,
            items=[
                {"product": self.product.pk, "quantity": 1},
            ],
        )

        Order.objects.filter(pk=second_order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        mock_expire.side_effect = [
            RuntimeError("Simulated failure"),
            True,
        ]

        output = StringIO()

        with self.assertLogs(
            "orders.management.commands.expire_orders",
            level="ERROR",
        ):
            call_command("expire_orders", stdout=output)

        self.assertEqual(mock_expire.call_count, 2)
        self.assertIn("expired=1", output.getvalue())
        self.assertIn("failed=1", output.getvalue())
