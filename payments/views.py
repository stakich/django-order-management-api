import logging

import stripe
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import (
    PaymentNotAllowedError,
    PaymentOrderNotFoundError,
    PaymentProviderError,
    PaymentServiceUnavailable,
)
from .models import Payment
from .services import PaymentService

logger = logging.getLogger(__name__)


class CheckoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="CheckoutResponse",
                fields={
                    "checkout_url": serializers.URLField(),
                },
            ),
        },
        description="Create or retrieve a Stripe Checkout session for an order.",
    )

    def post(self, request, pk):
        try:
            checkout_url = PaymentService.create_checkout_session(
                user=request.user,
                order_id=pk,
            )

        except PaymentOrderNotFoundError as exc:
            raise NotFound(str(exc)) from exc

        except PaymentNotAllowedError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        except PaymentProviderError as exc:
            raise PaymentServiceUnavailable() from exc

        return Response(
            {"checkout_url": checkout_url},
            status=status.HTTP_200_OK,
        )


class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={
            200: inline_serializer(
                name="StripeWebhookResponse",
                fields={
                    "received": serializers.BooleanField(),
                },
            ),
        },
        description="Receive and verify Stripe webhook events.",
    )

    def post(self, request):
        data = request.body
        header = request.headers.get("Stripe-Signature")

        try:
            event = stripe.Webhook.construct_event(
                data,
                header,
                settings.STRIPE_WEBHOOK_SECRET,
            )

        except ValueError:
            return Response(
                {"detail": "Invalid payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except stripe.error.SignatureVerificationError:
            return Response(
                {"detail": "Invalid Stripe signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )


        event_type = event["type"]

        supported_events = (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
            "checkout.session.async_payment_failed",
            "checkout.session.expired",
        )

        if event_type not in supported_events:
            return Response({"received": True}, status=200)

        session = event["data"]["object"]
        metadata = session.get("metadata") or {}
        payment_id = metadata.get("payment_id") if isinstance(metadata, dict) else None

        log_context = {
            "event_id": event.get("id"),
            "session_id": session.get("id"),
            "payment_id": payment_id,
            "payment_intent_id": session.get("payment_intent"),
        }

        if not payment_id:
            logger.warning("Stripe webhook missing payment ID: %s", log_context)
            return Response({"received": True}, status=200)

        if (
            not isinstance(payment_id, str)
            or not payment_id.isascii()
            or not payment_id.isdecimal()
            or not 0 < int(payment_id) <= 9223372036854775807
        ):
            logger.critical("Stripe webhook invalid payment ID: %s", log_context)
            return Response({"received": True}, status=200)

        try:
            if event_type in (
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
            ):
                if session.get("payment_status") == "paid":
                    PaymentService.handle_successful_checkout(session)

            elif event_type == "checkout.session.expired":
                PaymentService.handle_expired_checkout(session)

            elif event_type == "checkout.session.async_payment_failed":
                PaymentService.handle_failed_async_checkout(session)

        except (Payment.DoesNotExist, PaymentNotAllowedError):
            logger.critical(
                "Stripe webhook requires manual investigation: %s",
                log_context,
                exc_info=True,
            )

        return Response({"received": True}, status=200)

