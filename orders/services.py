from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from orders.exceptions import OrderCannotBeCancelledError, OrderCreationError, OrderNotFoundError
from orders.models import Order, OrderItem
from payments.exceptions import PaymentNotAllowedError, PaymentProviderError
from payments.models import Payment
from payments.services import PaymentService
from products.models import Product


class OrderService:

    @staticmethod
    def _restore_stock(order):
        quantities = {}

        for item in order.items.all():
            quantities[item.product_id] = (
                    quantities.get(item.product_id, 0)
                    + item.quantity
            )

        products = list(
            Product.objects
            .select_for_update()
            .filter(id__in=quantities)
            .order_by("id")
        )

        if len(products) != len(quantities):
            raise OrderCannotBeCancelledError(
                "Some order products are unavailable"
            )

        for product in products:
            product.stock += quantities[product.id]
            product.save(update_fields=["stock"])

    @staticmethod
    def create_order(user, items):
        if not items:
            raise ValueError("Order must contain at least one item")
        products_ids = set()
        for item in items:
            product_id = item["product"]
            product_quantity = item["quantity"]

            if type(product_id) is not int or product_id < 1:
                raise OrderCreationError("Product ID must be a positive integer")

            if type(product_quantity) is not int or product_quantity < 1:
                raise OrderCreationError("Quantity must be a positive integer")

            if product_id in products_ids:
                raise OrderCreationError("Product already in order")

            products_ids.add(product_id)

        with transaction.atomic():
            products = (
                Product.objects.select_for_update().filter(id__in=products_ids).order_by("id")
            )

            products = list(products)

            products_by_id = {product.id: product for product in products}

            if len(products) != len(products_ids):
                raise OrderCreationError("Some products are not available")

            for item in items:
                product = products_by_id[item["product"]]

                if product.stock < item["quantity"]:
                    raise OrderCreationError("Not enough stock for product")

                if not product.is_active:
                    raise OrderCreationError("Product is not active")

            order = Order.objects.create(user=user)

            for item in items:
                current_product = products_by_id[item["product"]]

                OrderItem.objects.create(
                    order=order,
                    product=current_product,
                    quantity=item["quantity"],
                    unit_price=current_product.price,
                )

                current_product.stock -= item["quantity"]
                current_product.save(update_fields=["stock"])

            return order

    @staticmethod
    def cancel_order(user, order_id):
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=order_id)
            except Order.DoesNotExist as exc:
                raise OrderNotFoundError("Order not found") from exc

            is_owner = order.user_id == user.id

            is_admin = UserProfile.objects.filter(user=user, role=UserProfile.Role.ADMIN).exists()

            if not is_owner and not is_admin:
                raise OrderNotFoundError("Order not found")

            if order.status != Order.Status.PENDING:
                raise OrderCannotBeCancelledError("Only pending orders can be cancelled")

            has_active_payment = Payment.objects.filter(
                order=order,
                status=Payment.Status.PENDING,
                checkout_status__in=[
                    Payment.CheckoutStatus.CREATING,
                    Payment.CheckoutStatus.READY,
                ],
            ).exists()

            if has_active_payment:
                raise OrderCannotBeCancelledError(
                    "Order cannot be cancelled while payment is in progress"
                )

            OrderService._restore_stock(order)

            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])

            return order

    @staticmethod
    def expire_order(order_id):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist as exc:
            raise OrderNotFoundError("Order not found") from exc

        if order.status != Order.Status.PENDING:
            return False

        if order.expires_at is None or order.expires_at > timezone.now():
            return False

        # Phase 1: Verify payment attempts without holding DB locks.
        verified_payments = {}

        for payment in Payment.objects.filter(order=order).order_by("id"):
            state = (payment.status, payment.checkout_status)

            if (
                    payment.status == Payment.Status.FAILED
                    and payment.checkout_status in (
                    Payment.CheckoutStatus.READY,
                    Payment.CheckoutStatus.EXPIRED,
            )
                    and payment.stripe_session_id
            ):
                verified_payments[payment.id] = state
                continue

            if (
                    state == (Payment.Status.PENDING, Payment.CheckoutStatus.NOT_STARTED)
                    and not payment.stripe_session_id
            ):
                verified_payments[payment.id] = state
                continue

            if (
                    payment.status == Payment.Status.PENDING
                    and payment.checkout_status == Payment.CheckoutStatus.CREATING
                    and not payment.stripe_session_id
            ):
                try:
                    PaymentService.recover_stuck_checkout(payment.id)
                except (PaymentNotAllowedError, PaymentProviderError):
                    return False

                # Process the updated payment on the next expiration attempt.
                return False


            if (
                    payment.status != Payment.Status.PENDING
                    or payment.checkout_status not in (
                    Payment.CheckoutStatus.READY,
                    Payment.CheckoutStatus.EXPIRED,
            )
                    or not payment.stripe_session_id
            ):
                return False

            if not PaymentService.ensure_checkout_expired(payment.id):
                return False

            verified_payments[payment.id] = (
                Payment.Status.PENDING,
                Payment.CheckoutStatus.EXPIRED,
            )

        # Phase 2: Recheck and update everything atomically.
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order_id)

            if order.status != Order.Status.PENDING:
                return False

            if order.expires_at is None or order.expires_at > timezone.now():
                return False

            payments = list(
                Payment.objects.select_for_update()
                .filter(order=order)
                .order_by("id")
            )

            if [p.id for p in payments] != list(verified_payments):
                return False

            for payment in payments:
                if (
                        payment.status,
                        payment.checkout_status,
                ) != verified_payments[payment.id]:
                    return False

            OrderService._restore_stock(order)

            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])

            return True
