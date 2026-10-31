from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import UserProfile

User = get_user_model()
REGISTER = '/api/v1/auth/register/'
LOGIN = '/api/v1/auth/login/'
ME = '/api/v1/auth/me/'


class RegistrationAPITests(APITestCase):
    def payload(self, **changes):
        data = {
            'username': 'customer',
            'email': 'customer@example.com',
            'password': 'StrongTestPassword123!',
            'password_confirm': 'StrongTestPassword123!',
        }
        data.update(changes)
        return data

    def test_register_creates_customer_with_hashed_password_and_no_secret_in_response(self):
        response = self.client.post(REGISTER, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='customer')
        self.assertTrue(user.check_password('StrongTestPassword123!'))
        self.assertNotEqual(user.password, 'StrongTestPassword123!')
        self.assertEqual(UserProfile.objects.get(user=user).role, UserProfile.Role.CUSTOMER)
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_confirm', response.data)

    def test_duplicate_email_is_rejected_case_insensitively_without_creating_user(self):
        first = self.client.post(REGISTER, self.payload(), format='json')
        self.assertEqual(first.status_code, 201)
        response = self.client.post(REGISTER, self.payload(username='other', email='CUSTOMER@example.com'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_password_mismatch_has_no_side_effects(self):
        response = self.client.post(REGISTER, self.payload(password_confirm='not-the-password'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(UserProfile.objects.exists())

    def test_missing_required_fields_are_rejected(self):
        for key in ('username', 'email', 'password', 'password_confirm'):
            with self.subTest(key=key):
                data = self.payload()
                del data[key]
                response = self.client.post(REGISTER, data, format='json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.count(), 0)


class AuthenticationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='customer', email='customer@example.com', password='StrongTestPassword123!')

    def test_valid_credentials_return_jwt_and_me_returns_only_safe_fields(self):
        login = self.client.post(LOGIN, {'username': 'customer', 'password': 'StrongTestPassword123!'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertIn('access', login.data)
        self.assertIn('refresh', login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        me = self.client.get(ME)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['id'], self.user.id)
        self.assertEqual(me.data['email'], 'customer@example.com')
        self.assertNotIn('password', me.data)

    def test_invalid_login_does_not_return_tokens(self):
        response = self.client.post(LOGIN, {'username': 'customer', 'password': 'incorrect'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access', response.data)

    def test_me_requires_valid_authentication(self):
        self.assertEqual(self.client.get(ME).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.token')
        self.assertEqual(self.client.get(ME).status_code, 401)
