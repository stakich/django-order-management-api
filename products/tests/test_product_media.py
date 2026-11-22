from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from products.models import Category, Product


class ProductMediaTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Furniture", slug="furniture")
        self.product = Product.objects.create(
            name="Chair",
            sku="CHAIR-1",
            category=self.category,
            price="49.00",
            stock=3,
        )

    def test_product_includes_category_name_and_empty_image(self):
        response = self.client.get(f"/api/v1/products/{self.product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["category_name"], "Furniture")
        self.assertIsNone(response.data["image_url"])

    def test_product_image_url_is_relative(self):
        buffer = BytesIO()
        Image.new("RGB", (2, 2)).save(buffer, format="PNG")

        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            upload = SimpleUploadedFile("chair.png", buffer.getvalue(), content_type="image/png")
            self.product.image.save("chair.png", upload, save=True)

            response = self.client.get(f"/api/v1/products/{self.product.id}/")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["image_url"].startswith("/media/products/"))

    def test_category_filter(self):
        other = Category.objects.create(name="Lighting", slug="lighting")
        Product.objects.create(name="Lamp", sku="LAMP-1", category=other, price="29", stock=1)

        response = self.client.get(f"/api/v1/products/?category={self.category.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([product["id"] for product in response.data["results"]], [self.product.id])
