from django.db import transaction
from orders.models import Order, OrderItem
from products.models import Product
from orders.exceptions import (
    OrderNotFoundError,
    OrderCannotBeCancelledError,
)


class OrderService:

    @staticmethod
    def create_order(user, items):
        if not items:
            raise ValueError("Order must contain at least one item")
        products_ids = set()
        for item in items:
            product_id = item["product"]
            product_quantity = item["quantity"]

            if type(product_id) is not int or product_id < 1:
                raise ValueError("Product ID must be a positive integer")

            if type(product_quantity) is not int or product_quantity < 1:
                raise ValueError("Quantity must be a positive integer")

            if product_id in products_ids:
                raise ValueError("Product already in order")

            products_ids.add(product_id)

        with transaction.atomic():
            products = (
                Product.objects.select_for_update().
                filter(id__in=products_ids)
                .order_by("id")
            )

            products = list(products)

            products_by_id = {
                product.id: product
                for product in products
            }

            if len(products) != len(products_ids):
                raise ValueError("Some products are not available")


            for item in items:
                product = products_by_id[item["product"]]

                if product.stock < item["quantity"]:
                    raise ValueError("Not enough stock for product")

                if not product.is_active:
                    raise ValueError("Product is not active")

            order = Order.objects.create(user=user)

            for item in items:
                current_product = products_by_id[item["product"]]

                OrderItem.objects.create(
                    order=order,
                    product=current_product,
                    quantity=item["quantity"],
                    unit_price=current_product.price
                )

                current_product.stock -= item["quantity"]
                current_product.save(update_fields=["stock"])


            return order

    @staticmethod
    def cancel_order(user, order_id):
        with transaction.atomic():

            try:
                order = (
                    Order.objects
                    .select_for_update()
                    .get(pk=order_id)
                )
            except Order.DoesNotExist as exc:
                raise OrderNotFoundError(
                    "Order not found"
                ) from exc

            is_owner = order.user_id == user.id
            is_admin = user.userprofile.role == "ADMIN"

            if not is_owner and not is_admin:
                raise OrderNotFoundError("Order not found")

            if order.status != Order.Status.PENDING:
                raise OrderCannotBeCancelledError(
                    "Only pending orders can be cancelled"
                )

            products_by_id = {}

            for item in order.items.all():
                products_by_id[item.product_id] = item.quantity

            products = list(
                Product.objects
                .select_for_update()
                .filter(id__in=products_by_id)
                .order_by("id")
            )

            if len(products) != len(products_by_id):
                raise OrderCannotBeCancelledError(
                    "Some order products are unavailable"
                )

            for product in products:
                product.stock += products_by_id[product.id]
                product.save(update_fields=["stock"])

            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])

            return order