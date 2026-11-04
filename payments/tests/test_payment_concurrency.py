"""PostgreSQL concurrency tests for payment/order state transitions.

Copy to payments/tests/test_concurrency.py. Run against a PostgreSQL TEST database.
No Stripe API calls are made.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from stripe import StripeObject

from orders.models import Order, OrderItem
from orders.services import OrderService
from orders.exceptions import OrderCannotBeCancelledError
from payments.models import Payment
from payments.services import PaymentService
from products.models import Category, Product


class PaymentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        if connections["default"].vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row-level locking")

        self.user = get_user_model().objects.create_user(
            username="concurrency_customer", password="test-password"
        )
        category = Category.objects.create(name="Concurrency", slug="concurrency")
        self.product = Product.objects.create(
            name="Test product",
            sku="CONCURRENT-1",
            category=category,
            price=Decimal("20.00"),
            stock=4,  # An order for 1 item has already reserved stock.
            is_active=True,
        )
        self.order = Order.objects.create(user=self.user)
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=1,
            unit_price=Decimal("20.00"),
        )
        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("20.00"),
            currency="EUR",
            status=Payment.Status.PENDING,
        )

    @staticmethod
    def _parallel(*operations):
        """Start independent DB connections at approximately the same time."""
        barrier = Barrier(len(operations))

        def worker(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(worker, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def test_two_concurrent_checkout_claims_only_one_succeeds(self):
        results = self._parallel(
            lambda: PaymentService.claim_checkout_creation(self.payment.pk),
            lambda: PaymentService.claim_checkout_creation(self.payment.pk),
        )

        self.assertCountEqual(results, [True, False])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.checkout_status, Payment.CheckoutStatus.CREATING)
        self.assertIsNotNone(self.payment.checkout_claimed_at)

    def test_checkout_claim_and_cancellation_cannot_both_succeed(self):
        def cancel():
            try:
                OrderService.cancel_order(self.user, self.order.pk)
                return True
            except OrderCannotBeCancelledError:
                return False

        claimed, cancelled = self._parallel(
            lambda: PaymentService.claim_checkout_creation(self.payment.pk),
            cancel,
        )

        self.assertNotEqual(claimed, cancelled)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.product.refresh_from_db()

        if claimed:
            self.assertEqual(self.order.status, Order.Status.PENDING)
            self.assertEqual(self.payment.checkout_status, Payment.CheckoutStatus.CREATING)
            self.assertEqual(self.product.stock, 4)
        else:
            self.assertEqual(self.order.status, Order.Status.CANCELLED)
            self.assertEqual(self.payment.checkout_status, Payment.CheckoutStatus.NOT_STARTED)
            self.assertEqual(self.product.stock, 5)

    def test_two_concurrent_success_webhooks_are_idempotent(self):
        self.payment.checkout_status = Payment.CheckoutStatus.READY
        self.payment.stripe_session_id = "cs_test_concurrent"
        self.payment.save(update_fields=["checkout_status", "stripe_session_id"])

        def webhook():
            # Separate StripeObject per worker: no shared mutable event.
            session = StripeObject.construct_from(
                {
                    "id": "cs_test_concurrent",
                    "mode": "payment",
                    "payment_status": "paid",
                    "amount_total": 2000,
                    "currency": "eur",
                    "metadata": {
                        "payment_id": str(self.payment.pk),
                        "order_id": str(self.order.pk),
                    },
                },
                None,
            )
            return PaymentService.handle_successful_checkout(session).pk

        results = self._parallel(webhook, webhook)
        self.assertEqual(results, [self.payment.pk, self.payment.pk])
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(
            Payment.objects.filter(order=self.order, status=Payment.Status.SUCCEEDED).count(),
            1,
        )
