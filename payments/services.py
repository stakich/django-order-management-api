import decimal
import logging
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from orders.models import Order
from payments.exceptions import (
    PaymentNotAllowedError,
    PaymentOrderNotFoundError,
    PaymentProviderError,
)
from payments.models import Payment

logger = logging.getLogger(__name__)

STRIPE_CURRENCY = "EUR"
STRIPE_PROVIDER = "STRIPE"


class PaymentService:
    @staticmethod
    def calculate_order_total(order):
        total = decimal.Decimal("0.00")

        for quantity, unit_price in order.items.values_list("quantity", "unit_price"):
            total += quantity * unit_price

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
    def _assert_session_matches(data, payment, *, expected_session_id=None):
        """Validate a Stripe Checkout Session against an existing Payment.

        The recorded session ID may be absent for an early webhook. Callers
        are responsible for deciding when that ID can safely be attached.
        """
        metadata = data.get("metadata") or {}
        session_id = data.get("id")

        if (
            not isinstance(metadata, dict)
            or not session_id
            or data.get("mode") != "payment"
            or metadata.get("payment_id") != str(payment.id)
            or metadata.get("order_id") != str(payment.order_id)
            or data.get("amount_total") != PaymentService.convert_to_cents(payment.amount)
            or (data.get("currency") or "").upper() != payment.currency.upper()
            or payment.provider != STRIPE_PROVIDER
            or (expected_session_id is not None and session_id != expected_session_id)
            or (payment.stripe_session_id is not None and session_id != payment.stripe_session_id)
        ):
            raise PaymentNotAllowedError("Stripe session does not match payment")

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
                raise PaymentNotAllowedError("Only pending orders can be paid")

            if order.expires_at is not None and order.expires_at <= timezone.now():
                raise PaymentNotAllowedError("Order reservation has expired")

            # The database allows only one pending or succeeded payment per order.
            payment = Payment.objects.filter(
                order=order,
                status__in=(Payment.Status.PENDING, Payment.Status.SUCCEEDED),
            ).first()

            if payment is not None and payment.status == Payment.Status.SUCCEEDED:
                raise PaymentNotAllowedError("Order already has a successful payment")

            total = PaymentService.calculate_order_total(order)

            if total <= decimal.Decimal("0.00"):
                raise PaymentNotAllowedError("Order total must be greater than zero")

            if payment is not None:
                if payment.amount != total or payment.currency != STRIPE_CURRENCY:
                    raise PaymentNotAllowedError(
                        "Payment amount or currency does not match the order"
                    )

            if payment is None:
                payment = Payment.objects.create(
                    order=order,
                    amount=total,
                    currency=STRIPE_CURRENCY,
                    status=Payment.Status.PENDING,
                    provider=STRIPE_PROVIDER,
                )

            return payment

    @staticmethod
    def create_stripe_session(payment):
        amount_in_cents = PaymentService.convert_to_cents(payment.amount)
        order_id = str(payment.order_id)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": STRIPE_CURRENCY.lower(),
                            "product_data": {"name": f"Order #{payment.order_id}"},
                            "unit_amount": amount_in_cents,
                        },
                        "quantity": 1,
                    }
                ],
                success_url=settings.STRIPE_SUCCESS_URL.replace("{ORDER_ID}", order_id),
                cancel_url=settings.STRIPE_CANCEL_URL.replace("{ORDER_ID}", order_id),
                metadata={
                    "order_id": order_id,
                    "payment_id": str(payment.id),
                },
                idempotency_key=f"checkout-payment-{payment.id}",
            )

        except (
            stripe.error.InvalidRequestError,
            stripe.error.AuthenticationError,
            stripe.error.PermissionError,
        ) as exc:
            # Stripe definitively rejected the request.
            # Restore the checkout state without holding locks during the API call.
            with transaction.atomic():
                Order.objects.select_for_update().get(pk=payment.order_id)
                locked_payment = Payment.objects.select_for_update().get(pk=payment.id)

                if (
                    locked_payment.status == Payment.Status.PENDING
                    and locked_payment.checkout_status == Payment.CheckoutStatus.CREATING
                    and locked_payment.stripe_session_id is None
                ):
                    locked_payment.checkout_status = Payment.CheckoutStatus.NOT_STARTED
                    locked_payment.checkout_claimed_at = None
                    locked_payment.save(
                        update_fields=[
                            "checkout_status",
                            "checkout_claimed_at",
                            "updated_at",
                        ]
                    )

            if isinstance(exc, stripe.error.InvalidRequestError):
                raise PaymentNotAllowedError(
                    "Checkout could not be created for this order"
                ) from exc

            raise PaymentProviderError("Stripe checkout configuration was rejected") from exc

        except stripe.error.StripeError as exc:
            raise PaymentProviderError("Unable to create Stripe checkout session") from exc

        return session

    @staticmethod
    def save_stripe_session(payment, session):
        with transaction.atomic():
            payment_order_id = Payment.objects.values_list("order_id", flat=True).get(id=payment.id)

            order = Order.objects.select_for_update().get(id=payment_order_id)

            locked_payment = Payment.objects.select_for_update().get(id=payment.id)

            if (
                locked_payment.stripe_session_id == session.id
                and locked_payment.checkout_status == Payment.CheckoutStatus.READY
                and (
                    (
                        locked_payment.status == Payment.Status.SUCCEEDED
                        and order.status == Order.Status.PAID
                    )
                    or (
                        locked_payment.status == Payment.Status.PENDING
                        and order.status == Order.Status.PENDING
                    )
                )
            ):
                return locked_payment

            # New session cannot be saved for a cancelled or paid order
            if order.status != Order.Status.PENDING:
                raise PaymentNotAllowedError("Order is no longer available for checkout")

            # Reject a different Stripe session
            if locked_payment.stripe_session_id is not None:
                raise PaymentNotAllowedError("Payment already has a different Stripe session")

            if (
                locked_payment.status != Payment.Status.PENDING
                or locked_payment.checkout_status != Payment.CheckoutStatus.CREATING
            ):
                raise PaymentNotAllowedError("Payment is no longer available for checkout")

            locked_payment.stripe_session_id = session.id
            locked_payment.checkout_status = Payment.CheckoutStatus.READY

            locked_payment.save(
                update_fields=[
                    "stripe_session_id",
                    "checkout_status",
                    "updated_at",
                ]
            )

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
        if payment.status != Payment.Status.PENDING:
            return False

        if payment.checkout_status != Payment.CheckoutStatus.CREATING:
            return False

        if payment.stripe_session_id is not None:
            return False

        if payment.checkout_claimed_at is None:
            return False

        now = timezone.now()

        # Wait before retrying the previous attempt
        if now - payment.checkout_claimed_at <= timedelta(minutes=10):
            return False

        # Do not retry beyond the conservative idempotency window
        if now - payment.created_at >= timedelta(hours=23):
            return False

        return True

    @staticmethod
    def claim_checkout_creation(payment_id):
        with transaction.atomic():
            payment_order_id = Payment.objects.values_list("order_id", flat=True).get(id=payment_id)

            order = Order.objects.select_for_update().get(id=payment_order_id)

            payment = Payment.objects.select_for_update().get(id=payment_id)

            if order.expires_at is not None and order.expires_at <= timezone.now():
                return False

            if order.status != Order.Status.PENDING:
                return False

            if payment.status != Payment.Status.PENDING:
                return False

            if (
                payment.checkout_status == Payment.CheckoutStatus.NOT_STARTED
                or PaymentService.can_retry_checkout_creation(payment)
            ):
                payment.checkout_status = Payment.CheckoutStatus.CREATING
                payment.checkout_claimed_at = timezone.now()

                payment.save(
                    update_fields=[
                        "checkout_status",
                        "checkout_claimed_at",
                        "updated_at",
                    ]
                )

                return True

            return False

    @staticmethod
    def get_existing_stripe_session(payment):
        if not payment.stripe_session_id:
            raise PaymentNotAllowedError("Payment does not have a Stripe session")

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.retrieve(payment.stripe_session_id)
        except stripe.error.StripeError as exc:
            raise PaymentProviderError("Unable to retrieve Stripe checkout session") from exc

        if session.status == "open" and session.payment_status == "unpaid":
            return session.url

        if session.status == "expired" and session.payment_status == "unpaid":
            PaymentService.handle_expired_checkout(session)

            raise PaymentNotAllowedError(
                "Stripe checkout session has expired. Please retry checkout."
            )

        raise PaymentNotAllowedError("Stripe checkout session is no longer available")

    @staticmethod
    def create_checkout_session(user, order_id):
        payment = PaymentService.get_or_create_payment(user=user, order_id=order_id)
        if payment.checkout_status == Payment.CheckoutStatus.EXPIRED:
            stripe.api_key = settings.STRIPE_SECRET_KEY

            try:
                stripe_session = stripe.checkout.Session.retrieve(payment.stripe_session_id)
            except stripe.error.StripeError as exc:
                logger.exception("Stripe Checkout session creation failed")
                raise PaymentProviderError("Unable to verify expired checkout session") from exc

            if stripe_session.status != "expired" or stripe_session.payment_status != "unpaid":
                raise PaymentNotAllowedError(
                    "Previous payment is not confirmed as expired and unpaid"
                )
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=payment.order_id)

                locked_payment = Payment.objects.select_for_update().get(id=payment.id)

                if order.status != Order.Status.PENDING:
                    raise PaymentNotAllowedError("Order is no longer pending")

                if (
                    locked_payment.status != Payment.Status.PENDING
                    or locked_payment.checkout_status != Payment.CheckoutStatus.EXPIRED
                    or locked_payment.stripe_session_id != stripe_session.id
                ):
                    raise PaymentNotAllowedError("Payment state has changed")

                current_total = PaymentService.calculate_order_total(order)

                if (
                    current_total != locked_payment.amount
                    or locked_payment.currency != STRIPE_CURRENCY
                ):
                    raise PaymentNotAllowedError("Order amount or currency has changed")

                locked_payment.status = Payment.Status.FAILED
                locked_payment.save(update_fields=["status", "updated_at"])

                payment = Payment.objects.create(
                    order=order,
                    amount=locked_payment.amount,
                    currency=locked_payment.currency,
                    status=Payment.Status.PENDING,
                    provider=STRIPE_PROVIDER,
                )

        if payment.checkout_status == Payment.CheckoutStatus.READY:
            return PaymentService.get_existing_stripe_session(payment)

        claimed = PaymentService.claim_checkout_creation(payment.id)

        if claimed:
            stripe_session = PaymentService.create_stripe_session(payment)

            payment = PaymentService.save_stripe_session(payment, stripe_session)

            if Order.objects.filter(
                pk=payment.order_id,
                status=Order.Status.PENDING,
                expires_at__lte=timezone.now(),
            ).exists():
                raise PaymentNotAllowedError("Order reservation has expired")

            return stripe_session.url
        else:
            raise PaymentNotAllowedError("Checkout creation is already in progress or unavailable")

    @staticmethod
    def handle_successful_checkout(session):
        session_data = session.to_dict()
        metadata = session_data.get("metadata") or {}
        payment_id = metadata.get("payment_id")

        if not payment_id:
            raise PaymentNotAllowedError("Stripe session does not contain payment_id")

        with transaction.atomic():
            payment = Payment.objects.get(id=payment_id)

            order = Order.objects.select_for_update().get(id=payment.order_id)

            payment = Payment.objects.select_for_update().get(id=payment_id)

            PaymentService._assert_session_matches(session_data, payment)

            if session["payment_status"] != "paid":
                raise PaymentNotAllowedError("Invalid Stripe payment")

            if payment.stripe_session_id is None:
                if (
                    payment.status == Payment.Status.PENDING
                    and order.status == Order.Status.PENDING
                    and payment.checkout_status == Payment.CheckoutStatus.CREATING
                ):
                    payment.stripe_session_id = session["id"]
                    payment.checkout_status = Payment.CheckoutStatus.READY
                else:
                    raise PaymentNotAllowedError("Unexpected payment state")

            # Already processed
            if payment.status == Payment.Status.SUCCEEDED and order.status == Order.Status.PAID:
                return payment

            # Validate current statuses
            if payment.status != Payment.Status.PENDING or order.status != Order.Status.PENDING:
                raise PaymentNotAllowedError("Invalid payment or order status")

            # Complete payment
            payment.status = Payment.Status.SUCCEEDED
            order.status = Order.Status.PAID

            payment.save(
                update_fields=[
                    "status",
                    "stripe_session_id",
                    "checkout_status",
                    "updated_at",
                ]
            )

            order.save(update_fields=["status", "updated_at"])

            return payment

    @staticmethod
    def handle_expired_checkout(session):
        with transaction.atomic():
            payment = Payment.objects.get(stripe_session_id=session["id"])

            order = Order.objects.select_for_update().get(id=payment.order_id)

            payment = Payment.objects.select_for_update().get(id=payment.id)

            if session["status"] != "expired" or session["payment_status"] != "unpaid":
                return payment

            if order.status != Order.Status.PENDING:
                return payment

            if (
                payment.status != Payment.Status.PENDING
                or payment.checkout_status != Payment.CheckoutStatus.READY
            ):
                return payment

            payment.checkout_status = Payment.CheckoutStatus.EXPIRED
            payment.save(update_fields=["checkout_status", "updated_at"])

            return payment

    @staticmethod
    def reconcile_stuck_checkout(payment_id, session_id):
        payment = Payment.objects.get(pk=payment_id)

        # Only recover abandoned checkout attempts.
        if (
            payment.status != Payment.Status.PENDING
            or payment.checkout_status != Payment.CheckoutStatus.CREATING
            or payment.stripe_session_id is not None
            or payment.checkout_claimed_at is None
            or timezone.now() - payment.created_at < timedelta(hours=23)
            or timezone.now() - payment.checkout_claimed_at < timedelta(minutes=10)
        ):
            raise PaymentNotAllowedError("Payment is not eligible for reconciliation")

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.StripeError as exc:
            raise PaymentProviderError("Unable to verify Stripe checkout session") from exc

        data = session.to_dict()
        PaymentService._assert_session_matches(
            data,
            payment,
            expected_session_id=session_id,
        )

        status = data.get("status")
        payment_status = data.get("payment_status")

        # Reuse the existing successful-payment handler.
        if status == "complete" and payment_status == "paid":
            return PaymentService.handle_successful_checkout(session)

        if (status, payment_status) not in [
            ("open", "unpaid"),
            ("expired", "unpaid"),
        ]:
            raise PaymentNotAllowedError("Stripe session state requires manual investigation")

        with transaction.atomic():
            # Consistent lock order: Order -> Payment.
            order = Order.objects.select_for_update().get(pk=payment.order_id)

            locked_payment = Payment.objects.select_for_update().get(pk=payment_id)

            if (
                order.status != Order.Status.PENDING
                or locked_payment.status != Payment.Status.PENDING
                or locked_payment.checkout_status != Payment.CheckoutStatus.CREATING
                or locked_payment.stripe_session_id is not None
            ):
                raise PaymentNotAllowedError("Payment state changed during reconciliation")

            locked_payment.stripe_session_id = session_id

            if status == "open":
                locked_payment.checkout_status = Payment.CheckoutStatus.READY
            else:
                locked_payment.checkout_status = Payment.CheckoutStatus.EXPIRED

            locked_payment.save(
                update_fields=[
                    "stripe_session_id",
                    "checkout_status",
                    "updated_at",
                ]
            )

            return locked_payment

    @staticmethod
    def reconcile_known_checkout(payment_id):
        payment = Payment.objects.get(pk=payment_id)

        if not payment.stripe_session_id:
            raise PaymentNotAllowedError("Payment does not have a Stripe session")

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.retrieve(payment.stripe_session_id)
        except stripe.error.StripeError as exc:
            raise PaymentProviderError("Unable to verify Stripe checkout session") from exc

        data = session.to_dict()
        PaymentService._assert_session_matches(
            data,
            payment,
            expected_session_id=payment.stripe_session_id,
        )

        status = data.get("status")
        payment_status = data.get("payment_status")

        if status == "complete" and payment_status == "paid":
            return PaymentService.handle_successful_checkout(session)

        if status == "expired" and payment_status == "unpaid":
            return PaymentService.handle_expired_checkout(session)

        if status == "complete" and payment_status == "unpaid":
            intent_ref = data.get("payment_intent")

            intent_id = (
                intent_ref
                if isinstance(intent_ref, str)
                else intent_ref.get("id")
                if intent_ref
                else None
            )

            if intent_id:
                try:
                    intent = stripe.PaymentIntent.retrieve(intent_id)
                except stripe.error.StripeError as exc:
                    raise PaymentProviderError("Unable to retrieve Stripe PaymentIntent") from exc

                if (
                    intent.id != intent_id
                    or intent.amount != PaymentService.convert_to_cents(payment.amount)
                    or intent.currency.upper() != payment.currency.upper()
                ):
                    raise PaymentNotAllowedError("PaymentIntent does not match payment")

                if intent.status == "canceled":
                    return PaymentService.handle_failed_async_checkout(session)

            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=payment.order_id)

                locked_payment = Payment.objects.select_for_update().get(pk=payment_id)

                if locked_payment.stripe_session_id != session.id:
                    raise PaymentNotAllowedError("Stripe session has changed")

                # A webhook may have completed the payment concurrently.
                if (
                    locked_payment.status == Payment.Status.SUCCEEDED
                    and order.status == Order.Status.PAID
                ):
                    return locked_payment

                # A failure webhook may already have been processed.
                if locked_payment.status == Payment.Status.FAILED:
                    if order.status != Order.Status.PENDING:
                        raise PaymentNotAllowedError("Unexpected order status for failed payment")

                    return locked_payment

                if (
                    order.status != Order.Status.PENDING
                    or locked_payment.status != Payment.Status.PENDING
                ):
                    raise PaymentNotAllowedError("Payment state has changed")

                if locked_payment.checkout_status == Payment.CheckoutStatus.CREATING:
                    locked_payment.checkout_status = Payment.CheckoutStatus.READY
                    locked_payment.save(update_fields=["checkout_status", "updated_at"])

                elif locked_payment.checkout_status != Payment.CheckoutStatus.READY:
                    raise PaymentNotAllowedError("Unexpected checkout state")

                return locked_payment

        if status == "open" and payment_status == "unpaid":
            payment.refresh_from_db(fields=["status", "checkout_status"])

            if (
                payment.status == Payment.Status.PENDING
                and payment.checkout_status == Payment.CheckoutStatus.READY
            ):
                return payment

        raise PaymentNotAllowedError("Stripe checkout session requires manual investigation")

    @staticmethod
    def ensure_checkout_expired(payment_id):
        try:
            payment = PaymentService.reconcile_known_checkout(payment_id)
        except (PaymentNotAllowedError, PaymentProviderError):
            return False

        if payment.status != Payment.Status.PENDING:
            return False

        if payment.checkout_status == Payment.CheckoutStatus.EXPIRED:
            return True

        if payment.checkout_status != Payment.CheckoutStatus.READY:
            return False

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.expire(
                payment.stripe_session_id,
            )
        except stripe.error.StripeError:
            logger.warning(
                "Unable to expire Stripe session for payment %s",
                payment_id,
                exc_info=True,
            )
            return False

        if (
            session["id"] != payment.stripe_session_id
            or session["status"] != "expired"
            or session["payment_status"] != "unpaid"
        ):
            return False

        updated_payment = PaymentService.handle_expired_checkout(session)

        return (
            updated_payment.status == Payment.Status.PENDING
            and updated_payment.checkout_status == Payment.CheckoutStatus.EXPIRED
        )

    @staticmethod
    def recover_stuck_checkout(payment_id):
        payment = Payment.objects.select_related("order").get(pk=payment_id)

        # Recover only expired orders with an abandoned checkout attempt.
        if (
            payment.order.status != Order.Status.PENDING
            or payment.order.expires_at is None
            or payment.order.expires_at > timezone.now()
            or not PaymentService.can_retry_checkout_creation(payment)
        ):
            return False

        original_claimed_at = payment.checkout_claimed_at

        # Retry with the original idempotency key and identical parameters.
        # Never return this Checkout URL to the customer.
        replayed_session = PaymentService.create_stripe_session(payment)

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            session = stripe.checkout.Session.retrieve(replayed_session.id)
        except stripe.error.StripeError as exc:
            raise PaymentProviderError("Unable to retrieve recovered Stripe session") from exc

        data = session.to_dict()
        PaymentService._assert_session_matches(
            data,
            payment,
            expected_session_id=replayed_session.id,
        )

        state = (data.get("status"), data.get("payment_status"))

        # The payment succeeded while we were recovering it.
        if state == ("complete", "paid"):
            PaymentService.handle_successful_checkout(session)
            return False

        # Save the recovered session ID, even if payment is unresolved.
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment.order_id)
            locked_payment = Payment.objects.select_for_update().get(pk=payment_id)

            if (
                order.status != Order.Status.PENDING
                or locked_payment.status != Payment.Status.PENDING
                or locked_payment.checkout_status != Payment.CheckoutStatus.CREATING
                or locked_payment.stripe_session_id is not None
                or locked_payment.checkout_claimed_at != original_claimed_at
            ):
                return False

            locked_payment.stripe_session_id = session.id

            if state == ("open", "unpaid"):
                locked_payment.checkout_status = Payment.CheckoutStatus.READY
            elif state == ("expired", "unpaid"):
                locked_payment.checkout_status = Payment.CheckoutStatus.EXPIRED

            locked_payment.save(
                update_fields=[
                    "stripe_session_id",
                    "checkout_status",
                    "updated_at",
                ]
            )

            return state in {
                ("open", "unpaid"),
                ("expired", "unpaid"),
            }

    @staticmethod
    def handle_failed_async_checkout(session):
        data = session.to_dict()
        metadata = data.get("metadata") or {}
        payment_id = metadata.get("payment_id")

        if not payment_id:
            raise PaymentNotAllowedError("Missing payment_id")

        payment_order_id = Payment.objects.values_list("order_id", flat=True).get(pk=payment_id)

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment_order_id)

            payment = Payment.objects.select_for_update().get(pk=payment_id)

            PaymentService._assert_session_matches(data, payment)

            if data.get("status") != "complete" or data.get("payment_status") != "unpaid":
                raise PaymentNotAllowedError("Invalid Stripe session")

            # A delayed failure must never overwrite a paid order.
            if payment.status == Payment.Status.SUCCEEDED and order.status == Order.Status.PAID:
                return payment

            # Duplicate webhook: already processed.
            if payment.status == Payment.Status.FAILED:
                return payment

            if order.status != Order.Status.PENDING or payment.status != Payment.Status.PENDING:
                raise PaymentNotAllowedError("Invalid payment state")

            if payment.stripe_session_id is None:
                if payment.checkout_status != Payment.CheckoutStatus.CREATING:
                    raise PaymentNotAllowedError("Unexpected checkout state")

                payment.stripe_session_id = data["id"]

            elif payment.checkout_status not in (
                Payment.CheckoutStatus.CREATING,
                Payment.CheckoutStatus.READY,
            ):
                raise PaymentNotAllowedError("Unexpected checkout state")

            payment.status = Payment.Status.FAILED
            payment.checkout_status = Payment.CheckoutStatus.READY

            payment.save(
                update_fields=[
                    "status",
                    "checkout_status",
                    "stripe_session_id",
                    "updated_at",
                ]
            )

            return payment
