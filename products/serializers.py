from rest_framework import serializers

from .models import Category, Product


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["id", "created_at", "category_name", "image_url"]

    def get_image_url(self, obj: Product) -> str | None:
        return obj.image.url if obj.image else None


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name cannot be empty")
        return value
