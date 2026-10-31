from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from django.db import (
    DatabaseError,
    close_old_connections,
    connection,
    transaction,
)
from products.models import Product, Category
from orders.models import Order, OrderItem
from orders.services import OrderService
from orders.exceptions import OrderCreationError


User = get_user_model()


class OrderConcurrencyTests(TransactionTestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="customer1",
            password="testpassword123"
        )

        self.user2 = User.objects.create_user(
            username="customer2",
            password="testpassword123"
        )

        self.category = Category.objects.create(
            name="Electronics",
            slug="electronics"
        )

        self.product = Product.objects.create(
            name="Laptop",
            sku="CONCURRENT-LAPTOP-001",
            price="1200.00",
            stock=1,
            is_active=True,
            category=self.category
        )

    def test_two_customers_order_last_product(self):
        product_id = self.product.id

        barrier = Barrier(2)

        def place_order(user_id):
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                user = User.objects.get(id=user_id)

                order = OrderService.create_order(
                    user=user,
                    items=[
                        {
                            "product": product_id,
                            "quantity":  1
                        }
                    ]
                )

                return "success"


            except OrderCreationError:

                return "insufficient_stock"

            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(place_order, self.user1.id),
                executor.submit(place_order, self.user2.id),
            ]

            results = [
                future.result(timeout=15)
                for future in futures
            ]

        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("insufficient_stock"), 1)

        self.product.refresh_from_db()

        self.assertEqual(self.product.stock, 0)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    def test_row_lock_blocks_second_transaction(self):
        lock_acquired = Event()
        second_attempting = Event()
        release_lock = Event()

        product_id = self.product.id

        def first_transaction():
            close_old_connections()

            try:
                with transaction.atomic():
                    Product.objects.select_for_update().get(
                        id=product_id
                    )

                    lock_acquired.set()

                    if not release_lock.wait(timeout=10):
                        raise TimeoutError("Release signal not received")
            finally:
                close_old_connections()

        def second_transaction():
            close_old_connections()

            try:
                if not lock_acquired.wait(timeout=5):
                    raise TimeoutError("First transaction did not lock")

                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SET LOCAL lock_timeout = '1000ms'"
                        )

                    second_attempting.set()

                    Product.objects.select_for_update().get(
                        id=product_id
                    )

                return "lock_acquired"

            except DatabaseError:
                return "lock_timeout"

            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(first_transaction)

            try:
                self.assertTrue(lock_acquired.wait(timeout=5))

                future_b = executor.submit(second_transaction)

                self.assertTrue(second_attempting.wait(timeout=5))

                result_b = future_b.result(timeout=5)

                self.assertEqual(result_b, "lock_timeout")

            finally:
                release_lock.set()
                future_a.result(timeout=15)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)