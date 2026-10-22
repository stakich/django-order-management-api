from django.urls import path
from .views import OrderListView, OrderDetailView, OrderCancelView

urlpatterns = [
    path("", OrderListView.as_view(), name="order-list-create"),
    path("<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),

]