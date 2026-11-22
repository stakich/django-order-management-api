from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0006_product_product_stock_gte_0"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="products/"),
        ),
    ]
