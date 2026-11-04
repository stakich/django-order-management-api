import logging

import stripe

from django.conf import settings

from rest_framework import generics, status
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

        try:
            if event["type"] in (
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
            ):
                session = event["data"]["object"]

                if session["payment_status"] == "paid":
                    PaymentService.handle_successful_checkout(session)

            elif event["type"] == "checkout.session.expired":
                session = event["data"]["object"]

                PaymentService.handle_expired_checkout(session)

        except Payment.DoesNotExist:
            logger.exception(
                "Stripe webhook: Payment not found"
            )

            return Response(
                {"detail": "Payment not found yet"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except PaymentNotAllowedError:
            logger.exception(
                "Stripe webhook: Payment validation failed"
            )

            return Response(
                {"detail": "Unable to process payment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"received": True},
            status=status.HTTP_200_OK,
        )