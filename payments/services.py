import decimal
import stripe
from django.utils import timezone
from datetime import timedelta


from django.conf import settings
from django.db import transaction
from orders.models import Order
from payments.models import Payment
from payments.exceptions import PaymentOrderNotFoundError, PaymentNotAllowedError, PaymentProviderError

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
        try:

            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
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
        except stripe.error.StripeError as exc:
            raise PaymentProviderError(
                "Unable to create Stripe checkout session"
            ) from exc
        return session

    @staticmethod
    def save_stripe_session(payment, session):
        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().get(
                id=payment.id
            )
            if locked_payment.stripe_session_id  == session.id and locked_payment.checkout_status == Payment.CheckoutStatus.READY:
                return locked_payment

            if (
                    locked_payment.stripe_session_id is not None
                    and locked_payment.stripe_session_id != session.id
            ):
                raise PaymentNotAllowedError(
                    "Payment already has a different Stripe session"
                )

            if locked_payment.checkout_status != Payment.CheckoutStatus.CREATING:
                raise PaymentNotAllowedError()

            if locked_payment.status != Payment.Status.PENDING:
                raise PaymentNotAllowedError(
                    "Payment is no longer pending"
                )

            locked_payment.stripe_session_id = session.id
            locked_payment.checkout_status = Payment.CheckoutStatus.READY
            locked_payment.save(update_fields=["stripe_session_id", "updated_at", "checkout_status"])

        return locked_payment

    @staticmethod
    def is_checkout_stuck(payment):
        if payment.checkout_status != Payment.CheckoutStatus.CREATING:
            return False

        if payment.checkout_claimed_at is None:
            return False

        elapsed = timezone.now() - payment.checkout_claimed_at

        if elapsed > timedelta(minutes=10):
            return True

        return False

    @staticmethod
    def can_retry_checkout_creation(payment):
        if payment.checkout_status != Payment.CheckoutStatus.CREATING:
            return False

        if payment.stripe_session_id is not None:
            return False

        if payment.checkout_claimed_at is None:
            return False

        if payment.status != Payment.Status.PENDING:
            return False

        elapsed = timezone.now() - payment.checkout_claimed_at

        if not (timedelta(minutes=10) < elapsed < timedelta(minutes=20)):
            return False

        return True

    @staticmethod
    def claim_checkout_creation(payment_id):
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)

            if payment.checkout_status == Payment.CheckoutStatus.NOT_STARTED:
                payment.checkout_status = Payment.CheckoutStatus.CREATING
                payment.checkout_claimed_at = timezone.now()

                payment.save(
                    update_fields=["checkout_status", "updated_at", "checkout_claimed_at"]
                )
                return True

            return False

    @staticmethod
    def get_existing_stripe_session(payment):
        if not payment.stripe_session_id:
            raise PaymentNotAllowedError(
                "Payment does not have a Stripe session"
            )

        stripe.api_key = settings.STRIPE_SECRET_KEY

        session = stripe.checkout.Session.retrieve(
            payment.stripe_session_id
        )

        if session.status == "open" and session.payment_status == "unpaid":
            return session.url

        if session.status == "expired":
            raise PaymentNotAllowedError(
                "Stripe checkout session has expired"
            )

        raise PaymentNotAllowedError(
            "Stripe checkout session is no longer available"
        )

    @staticmethod
    def create_checkout_session(user, order_id):
        payment = PaymentService.get_or_create_payment(
            user=user,
            order_id=order_id
        )
        if payment.checkout_status == Payment.CheckoutStatus.EXPIRED:
            stripe.api_key = settings.STRIPE_SECRET_KEY

            try:
                stripe_session = stripe.checkout.Session.retrieve(
                    payment.stripe_session_id
                )
            except stripe.error.StripeError as exc:
                raise PaymentProviderError(
                    "Unable to verify expired checkout session"
                ) from exc


            if (
                stripe_session.status != "expired"
                or stripe_session.payment_status != "unpaid"
            ):
                raise PaymentNotAllowedError(
                    "Previous payment is not confirmed as expired and unpaid"
                )
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=payment.order_id)

                locked_payment = Payment.objects.select_for_update().get(
                    id=payment.id
                )

                if order.status != Order.Status.PENDING:
                    raise PaymentNotAllowedError("Order is no longer pending")


                if (
                    locked_payment.status != Payment.Status.PENDING
                    or locked_payment.checkout_status != Payment.CheckoutStatus.EXPIRED
                    or locked_payment.stripe_session_id != stripe_session.id
                ):
                    raise PaymentNotAllowedError(
                        "Payment state has changed"
                    )

                current_total = PaymentService.calculate_order_total(order)

                if (
                        current_total != locked_payment.amount
                        or locked_payment.currency != "EUR"
                ):
                    raise PaymentNotAllowedError(
                        "Order amount or currency has changed"
                    )

                locked_payment.status = Payment.Status.FAILED
                locked_payment.save(update_fields=["status", "updated_at"])

                payment = Payment.objects.create(
                    order=order,
                    amount=locked_payment.amount,
                    currency=locked_payment.currency,
                    status=Payment.Status.PENDING,
                    provider="STRIPE",
                )

        if payment.checkout_status == Payment.CheckoutStatus.READY:
            return PaymentService.get_existing_stripe_session(payment)

        claimed = PaymentService.claim_checkout_creation(payment.id)

        if claimed:
            stripe_session = PaymentService.create_stripe_session(payment)

            payment = PaymentService.save_stripe_session(payment, stripe_session)

            return stripe_session.url
        else:
            raise PaymentNotAllowedError("Checkout creation is already in progress or unavailable")

    @staticmethod
    def handle_successful_checkout(session):
        metadata = session.to_dict().get("metadata") or {}
        payment_id = metadata.get("payment_id")

        if not payment_id:
            raise PaymentNotAllowedError(
                "Stripe session does not contain payment_id"
            )

        with transaction.atomic():
            payment = Payment.objects.get(id=payment_id)

            order = Order.objects.select_for_update().get(
                id=payment.order_id
            )

            payment = Payment.objects.select_for_update().get(
                id=payment_id
            )

            # Validate Stripe payment
            if (
                    payment.stripe_session_id != session["id"]
                    or session["payment_status"] != "paid"
                    or session["amount_total"] != PaymentService.convert_to_cents(payment.amount)
                    or session["currency"].upper() != payment.currency.upper()
            ):
                raise PaymentNotAllowedError("Invalid Stripe payment")

            # Already processed
            if (
                    payment.status == Payment.Status.SUCCEEDED
                    and order.status == Order.Status.PAID
            ):
                return payment

            # Validate current statuses
            if (
                    payment.status != Payment.Status.PENDING
                    or order.status != Order.Status.PENDING
            ):
                raise PaymentNotAllowedError("Invalid payment or order status")

            # Complete payment
            payment.status = Payment.Status.SUCCEEDED
            order.status = Order.Status.PAID

            payment.save(update_fields=["status", "updated_at"])
            order.save(update_fields=["status"])

            return payment

    @staticmethod
    def handle_expired_checkout(session):
        with transaction.atomic():
            payment = Payment.objects.get(
                stripe_session_id=session["id"]
            )

            order = Order.objects.select_for_update().get(
                id=payment.order_id
            )

            payment = Payment.objects.select_for_update().get(
                id=payment.id
            )

            if (
                    payment.status != Payment.Status.PENDING
                    or payment.checkout_status != Payment.CheckoutStatus.READY
            ):
                return payment

            

