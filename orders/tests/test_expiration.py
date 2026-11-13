from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from orders.models import Order
from orders.services import OrderService
from payments.models import Payment
from products.models import Category, Product

User = get_user_model()


class OrderExpirationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            password="testpassword123",
        )

        category = Category.objects.create(
            name="Electronics",
            slug="electronics",
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="EXPIRATION-001",
            price="1000.00",
            stock=5,
            category=category,
            is_active=True,
        )

        self.order = OrderService.create_order(
            user=self.user,
            items=[
                {"product": self.product.id, "quantity": 2}
            ],
        )

    def expire_reservation(self):
        Order.objects.filter(pk=self.order.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

    def test_expired_order_restores_stock(self):
        self.expire_reservation()

        result = OrderService.expire_order(self.order.id)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)

    def test_active_order_is_not_cancelled(self):
        result = OrderService.expire_order(self.order.id)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)

    def test_expiration_is_idempotent(self):
        self.expire_reservation()

        first_result = OrderService.expire_order(self.order.id)
        second_result = OrderService.expire_order(self.order.id)

        self.product.refresh_from_db()

        self.assertTrue(first_result)
        self.assertFalse(second_result)
        self.assertEqual(self.product.stock, 5)

    def test_order_with_not_started_payment_is_cancelled(self):
        self.expire_reservation()

        Payment.objects.create(
            order=self.order,
            amount="2000.00",
        )

        result = OrderService.expire_order(self.order.id)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(
            self.order.status,
            Order.Status.CANCELLED,
        )
        self.assertEqual(self.product.stock, 5)

    def test_order_with_creating_payment_is_not_cancelled(self):
        self.expire_reservation()

        Payment.objects.create(
            order=self.order,
            amount="2000.00",
            checkout_status=Payment.CheckoutStatus.CREATING,
            checkout_claimed_at=timezone.now(),
        )

        result = OrderService.expire_order(self.order.id)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertFalse(result)
        self.assertEqual(
            self.order.status,
            Order.Status.PENDING,
        )
        self.assertEqual(self.product.stock, 3)

    def test_expired_order_with_failed_async_payment_is_cancelled(self):
        self.expire_reservation()

        Payment.objects.create(
            order=self.order,
            amount=Decimal("2000.00"),
            status=Payment.Status.FAILED,
            checkout_status=Payment.CheckoutStatus.READY,
            stripe_session_id="cs_test_async_failed",
        )

        result = OrderService.expire_order(self.order.id)

        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertTrue(result)
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)
