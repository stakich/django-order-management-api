from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Product, Category


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "price",
        "stock",
        "category",
        "is_active",
    )

    search_fields = ("name", "sku")
    list_filter = ("category", "is_active")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
        "is_active",
    )

    search_fields = ("name",)