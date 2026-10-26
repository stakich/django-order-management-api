import decimal

import stripe

from django.conf import settings
from django.db import transaction
from orders.models import Order
from payments.models import Payment
from payments.exceptions import PaymentOrderNotFoundError, PaymentNotAllowedError

class PaymentService:

    @staticmethod
    def calculate_order_total(order):
        total = decimal.Decimal("0.00")

        for item in order.items.all():
            total += item.quantity * item.unit_price

        return total

    @staticmethod
    def convert_to_cents(amount):
        if not amount.is_finite() or amount <= decimal.Decimal("0.00"):
            raise ValueError("Amount must be greater than zero")

        if amount != amount.quantize(decimal.Decimal("0.01")):
            raise ValueError("Amount cannot have fractional cents")



        amount_in_cents = int(amount * 100)

        return amount_in_cents

    @staticmethod
    def get_or_create_payment(user, order_id):
        with transaction.atomic():

            try:
                order = Order.objects.select_for_update().get(id=order_id)

            except Order.DoesNotExist as exc:
                raise PaymentOrderNotFoundError("Order not found ") from exc

            if order.user_id != user.id:
                raise PaymentOrderNotFoundError("Order not found")

            if order.status != Order.Status.PENDING:
                raise PaymentNotAllowedError(
                    "Only pending orders can be paid"
                )

            if Payment.objects.filter(
                    order=order,
                    status=Payment.Status.SUCCEEDED
            ).exists():
                raise PaymentNotAllowedError(
                    "Order already has a successful payment"
                )

            total = PaymentService.calculate_order_total(order)

            payment = Payment.objects.filter(
                order=order,
                status=Payment.Status.PENDING,
            ).first()

            if payment is not None:
                if payment.amount != total or payment.currency != "EUR":
                    raise PaymentNotAllowedError(
                        "Payment amount or currency does not match the order"
                    )

            if payment is None:

                payment = Payment.objects.create(
                    order=order,
                    amount=total,
                    currency="EUR",
                    status=Payment.Status.PENDING,
                    provider="STRIPE"
                )

            return payment

    @staticmethod
    def create_stripe_session(payment):
        amount_in_cents = PaymentService.convert_to_cents(payment.amount)
        stripe.api_key = settings.STRIPE_SECRET_KEY

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {
                            "name": f"Order #{payment.order_id}"
                        },
                        "unit_amount": amount_in_cents,
                    },
                    "quantity": 1,
                }
            ],
            success_url="http://localhost:8000/payment/success/",
            cancel_url="http://localhost:8000/payment/cancel/",
            metadata={
                "order_id": str(payment.order_id),
                "payment_id": str(payment.id),
            },
            idempotency_key=f"checkout-payment-{payment.id}",
        )
        return session

    @staticmethod
    def save_stripe_session(payment, session):
        payment.stripe_session_id = session.id
        payment.save(update_fields=["stripe_session_id", "updated_at"])

        return payment

    @staticmethod
    def claim_checkout_creation(payment_id):
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)

            if payment.checkout_status == Payment.CheckoutStatus.NOT_STARTED:
                payment.checkout_status = Payment.CheckoutStatus.CREATING

                payment.save(
                    update_fields=["checkout_status", "updated_at"]
                )
                return True

            return False