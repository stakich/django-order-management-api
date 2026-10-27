from django.urls import path
from .views import CheckoutView, StripeWebhookView

urlpatterns = [
    path(
        "orders/<int:pk>/checkout/",
        CheckoutView.as_view(),
        name="order-checkout",
    ),
    path(
        "payments/stripe/webhook/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),
]