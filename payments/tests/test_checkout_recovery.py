from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import stripe
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from products.models import Product, Category
from orders.models import Order, OrderItem
from payments.exceptions import PaymentProviderError
from payments.models import Payment
from payments.services import PaymentService


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
class CheckoutRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="checkout_tester",
            password="test-password"
        )

        cls.category = Category.objects.create(
            name="Test Category",
            slug="test-category"
        )

        cls.product = Product.objects.create(
            name="Test Product",
            sku="TEST-001",
            price=Decimal("19.99"),
            stock=10,
            category=cls.category,
            is_active=True
        )

        cls.order = Order.objects.create(user=cls.user)

        OrderItem.objects.create(
            order=cls.order,
            product=cls.product,
            quantity=1,
            unit_price=Decimal("19.99")
        )

    def setUp(self):
        self.payment = Payment.objects.create(
            order=self.order,
            amount=Decimal("19.99"),
            currency="EUR",
            status=Payment.Status.PENDING,
        )

    @patch("payments.services.stripe.checkout.Session.create")
    def test_retry_uses_identical_stripe_parameters(self, mock_create):
        mock_create.return_value = SimpleNamespace(
            id="cs_test_same", url="https://checkout.stripe.com/test"
        )

        PaymentService.create_stripe_session(self.payment)
        PaymentService.create_stripe_session(self.payment)

        self.assertEqual(mock_create.call_count, 2)
        first = mock_create.call_args_list[0].kwargs
        second = mock_create.call_args_list[1].kwargs

        self.assertEqual(first, second)
        self.assertEqual(
            first["idempotency_key"],
            f"checkout-payment-{self.payment.id}",
        )
        self.assertEqual(
            first["line_items"][0]["price_data"]["unit_amount"], 1999
        )
        self.assertEqual(first["metadata"]["payment_id"], str(self.payment.id))
        self.assertEqual(first["metadata"]["order_id"], str(self.order.id))

    @patch("payments.services.stripe.checkout.Session.create")
    def test_stripe_timeout_does_not_mark_checkout_ready(self, mock_create):
        mock_create.side_effect = stripe.error.APIConnectionError(
            "Simulated lost Stripe response"
        )

        with self.assertRaises(PaymentProviderError):
            PaymentService.create_checkout_session(self.user, self.order.id)

        self.payment.refresh_from_db()
        self.assertEqual(
            self.payment.checkout_status, Payment.CheckoutStatus.CREATING
        )
        self.assertIsNone(self.payment.stripe_session_id)
        self.assertIsNotNone(self.payment.checkout_claimed_at)
        mock_create.assert_called_once()

    @patch("payments.services.stripe.checkout.Session.create")
    def test_recovery_after_timeout_reuses_same_payment(self, mock_create):
        mock_create.side_effect = [
            stripe.error.APIConnectionError("Simulated timeout"),
            SimpleNamespace(
                id="cs_test_recovered",
                url="https://checkout.stripe.com/recovered",
            ),
        ]

        with self.assertRaises(PaymentProviderError):
            PaymentService.create_checkout_session(self.user, self.order.id)

        original_payment_id = self.payment.id

        # Simulate a payment whose original attempt was 11 minutes ago.
        claimed_at = timezone.now() - timedelta(minutes=11)
        Payment.objects.filter(pk=self.payment.id).update(
            checkout_claimed_at=claimed_at
        )

        # Payment.created_at must also be within the permitted recovery window.
        url = PaymentService.create_checkout_session(self.user, self.order.id)

        self.assertEqual(url, "https://checkout.stripe.com/recovered")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.id, original_payment_id)
        self.assertEqual(
            self.payment.checkout_status, Payment.CheckoutStatus.READY
        )
        self.assertEqual(self.payment.stripe_session_id, "cs_test_recovered")
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

        first = mock_create.call_args_list[0].kwargs
        second = mock_create.call_args_list[1].kwargs
        self.assertEqual(first, second)

    @patch("payments.services.stripe.checkout.Session.create")
    def test_second_claim_cannot_start_another_stripe_request(self, mock_create):
        self.assertTrue(PaymentService.claim_checkout_creation(self.payment.id))
        self.assertFalse(PaymentService.claim_checkout_creation(self.payment.id))

        self.payment.refresh_from_db()
        self.assertEqual(
            self.payment.checkout_status, Payment.CheckoutStatus.CREATING
        )
        mock_create.assert_not_called()

    def test_retry_is_disallowed_after_payment_age_limit(self):
        Payment.objects.filter(pk=self.payment.id).update(
            checkout_status=Payment.CheckoutStatus.CREATING,
            checkout_claimed_at=timezone.now() - timedelta(minutes=11),
            created_at=timezone.now() - timedelta(minutes=25),
        )
        self.payment.refresh_from_db()

        self.assertFalse(
            PaymentService.can_retry_checkout_creation(self.payment)
        )
