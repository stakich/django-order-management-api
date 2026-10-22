from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from unittest.mock import patch
from django.db import DatabaseError
from django.db import transaction



from orders.models import Order, OrderItem
from orders.services import OrderService
from products.models import Product, Category

User = get_user_model()


class OrderServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testcustomer",
            password="testpassword123"
        )

        self.category = Category.objects.create(
            name="Electronics",
            slug="electronics"
        )

        self.product = Product.objects.create(
            name="Laptop",
            description="Test laptop",
            sku="TEST-001",
            price="1200.00",
            stock=10,
            category=self.category,
            is_active=True
        )

    def test_create_order_successfully(self):
        order = OrderService.create_order(
            user=self.user,
            items=[
                {
                    "product": self.product.id,
                    "quantity": 2
                }
            ]
        )

        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(Order.objects.count(), 1)

        self.assertEqual(order.items.count(), 1)

        order_item = order.items.first()

        self.assertEqual(order_item.product_id, self.product.id)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.unit_price, Decimal("1200.00"))

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, 8)

    def test_transaction_rollback(self):
        initial_stock = self.product.stock

        with self.assertRaises(ValueError):
            with transaction.atomic():
                order = Order.objects.create(user=self.user)

                OrderItem.objects.create(
                    order=order,
                    product=self.product,
                    quantity=2,
                    unit_price=self.product.price
                )

                self.product.stock -= 2
                self.product.save(update_fields=["stock"])

                raise ValueError("Simulated database failure")

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, initial_stock)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_order_service_rollback(self):
        initial_stock = self.product.stock

        with patch(
                "orders.services.OrderItem.objects.create",
                side_effect=DatabaseError("Simulated failure")
        ):
            with self.assertRaises(DatabaseError):
                OrderService.create_order(
                    user=self.user,
                    items=[
                        {
                            "product": self.product.id,
                            "quantity": 2
                        }
                    ]
                )

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, initial_stock)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)