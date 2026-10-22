from urllib import request

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound

from orders.exceptions import OrderNotFoundError, OrderCannotBeCancelledError
from orders.models import Order
from orders.serializers import OrderCreateSerializer, OrderSerializer
from orders.services import OrderService
from orders.utils.transaction_retry import retry_on_serialization_failure

class OrderListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user

        queryset = ((Order.objects
                    .order_by("-created_at"))
                    .prefetch_related("items__product"))

        if current_user.userprofile.role == "ADMIN":
            return queryset

        return queryset.filter(user=current_user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrderCreateSerializer

        return OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            order = retry_on_serialization_failure(
                operation=lambda: OrderService.create_order(
                    user=request.user,
                    items=serializer.validated_data["items"]
                ),
                max_attempts=3
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        order_serializer = OrderSerializer(order)

        return Response(order_serializer.data, status=status.HTTP_201_CREATED)

class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user

        queryset = ((Order.objects
                    .order_by("-created_at"))
                    .prefetch_related("items"))

        if current_user.userprofile.role == "ADMIN":
            return queryset

        return queryset.filter(user=current_user)

class OrderCancelView(generics.GenericAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        try:
            order = retry_on_serialization_failure(
                operation=lambda: OrderService.cancel_order(
                    user=request.user,
                    order_id=pk
                ),
                max_attempts=3
            )
        except OrderNotFoundError as exc:
            raise NotFound(str(exc)) from exc

        except OrderCannotBeCancelledError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        serializer = self.get_serializer(order)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )




