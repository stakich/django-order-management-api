from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from orders.models import Order, OrderItem
from payments.models import Payment
from payments.services import PaymentService
from products.models import Category, Product

User = get_user_model()


class PaymentContractTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='strong-pass123')
        self.other = User.objects.create_user(username='other', password='strong-pass123')
        UserProfile.objects.create(user=self.owner)
        UserProfile.objects.create(user=self.other)
        category = Category.objects.create(name='Hardware', slug='hardware')
        product = Product.objects.create(name='Laptop', sku='LAP-1', price='10.00', stock=3, category=category)
        self.order = Order.objects.create(user=self.owner)
        OrderItem.objects.create(order=self.order, product=product, quantity=2, unit_price=Decimal('10.00'))
        self.url = f'/api/v1/orders/{self.order.id}/checkout/'

    def test_non_owner_cannot_create_checkout_and_no_payment_is_created(self):
        self.client.force_authenticate(self.other)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Payment.objects.exists())

    def test_anonymous_checkout_is_denied(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)
        self.assertFalse(Payment.objects.exists())

    def test_checkout_uses_order_snapshot_amount_and_saves_stripe_session(self):
        self.client.force_authenticate(self.owner)
        session = SimpleNamespace(id='cs_test_123', url='https://checkout.stripe.com/test')
        with patch('payments.services.stripe.checkout.Session.create', return_value=session) as create:
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkout_url'], session.url)
        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.amount, Decimal('20.00'))
        self.assertEqual(payment.currency, 'EUR')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.checkout_status, Payment.CheckoutStatus.READY)
        self.assertEqual(payment.stripe_session_id, session.id)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs['line_items'][0]['price_data']['unit_amount'], 2000)
        self.assertEqual(kwargs['metadata']['payment_id'], str(payment.id))
        self.assertEqual(kwargs['idempotency_key'], f'checkout-payment-{payment.id}')

    def test_repeated_checkout_reuses_existing_stripe_session(self):
        self.client.force_authenticate(self.owner)
        session = SimpleNamespace(id='cs_test_123', url='https://checkout.stripe.com/test')
        retrieved = SimpleNamespace(status='open', payment_status='unpaid', url=session.url)
        with patch('payments.services.stripe.checkout.Session.create', return_value=session) as create, patch('payments.services.stripe.checkout.Session.retrieve', return_value=retrieved) as retrieve:
            first = self.client.post(self.url)
            second = self.client.post(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['checkout_url'], second.data['checkout_url'])
        self.assertEqual(create.call_count, 1)
        retrieve.assert_called_once_with('cs_test_123')
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    def test_payment_cents_validation(self):
        for value in ('0.00', '-1.00', '1.001'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PaymentService.convert_to_cents(Decimal(value))
        self.assertEqual(PaymentService.convert_to_cents(Decimal('12.34')), 1234)

    def test_successful_payment_is_idempotent_and_rejects_amount_mismatch(self):
        payment = Payment.objects.create(order=self.order, amount=Decimal('20.00'), currency='EUR', stripe_session_id='cs_test_123', checkout_status=Payment.CheckoutStatus.READY)
        def event(amount):
            return {
                'id': 'cs_test_123', 'payment_status': 'paid', 'amount_total': amount,
                'currency': 'eur', 'metadata': {'payment_id': str(payment.id)},
            }
        from stripe import StripeObject
        bad = StripeObject.construct_from(event(1999), None)
        from payments.exceptions import PaymentNotAllowedError
        with self.assertRaises(PaymentNotAllowedError):
            PaymentService.handle_successful_checkout(bad)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        good = StripeObject.construct_from(event(2000), None)
        PaymentService.handle_successful_checkout(good)
        PaymentService.handle_successful_checkout(good)
        payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(Payment.objects.filter(order=self.order).count(), 1)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_invalid_webhook_payload_is_rejected(self):
        response = self.client.post('/api/v1/payments/stripe/webhook/', data=b'not-json', content_type='application/json', HTTP_STRIPE_SIGNATURE='invalid')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.exists())
