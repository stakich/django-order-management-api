from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from products.models import Category, Product

User = get_user_model()
URL = '/api/v1/products/'


class ProductAPITests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Hardware', slug='hardware')
        self.visible = Product.objects.create(name='Laptop', sku='LAP-1', price='100.00', stock=3, category=self.category)
        self.hidden = Product.objects.create(name='Hidden', sku='HID-1', price='20.00', stock=1, category=self.category, is_active=False)
        self.customer = User.objects.create_user(username='customer', password='strong-pass123')
        self.admin = User.objects.create_user(username='adminuser', password='strong-pass123')
        UserProfile.objects.create(user=self.customer)
        UserProfile.objects.create(user=self.admin, role=UserProfile.Role.ADMIN)

    def test_anonymous_list_excludes_inactive_products(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        ids = {item['id'] for item in response.data['results']}
        self.assertIn(self.visible.id, ids)
        self.assertNotIn(self.hidden.id, ids)

    def test_anonymous_cannot_retrieve_inactive_product(self):
        self.assertEqual(self.client.get(f'{URL}{self.hidden.id}/').status_code, 404)

    def test_admin_can_retrieve_inactive_product(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'{URL}{self.hidden.id}/').status_code, 200)

    def test_anonymous_and_customer_cannot_mutate_catalog(self):
        payload = {'name': 'New', 'sku': 'NEW-1', 'price': '15.00', 'stock': 3, 'category': self.category.id}
        self.assertIn(self.client.post(URL, payload, format='json').status_code, (401, 403))
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(URL, payload, format='json').status_code, 403)
        self.assertEqual(self.client.delete(f'{URL}{self.visible.id}/').status_code, 403)
        self.assertFalse(Product.objects.filter(sku='NEW-1').exists())

    def test_admin_can_create_product(self):
        self.client.force_authenticate(self.admin)
        payload = {'name': 'Mouse', 'sku': 'MOU-1', 'price': '19.99', 'stock': 5, 'category': self.category.id}
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Product.objects.filter(sku='MOU-1', stock=5).exists())

    def test_database_rejects_negative_stock(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.filter(pk=self.visible.pk).update(stock=-1)
