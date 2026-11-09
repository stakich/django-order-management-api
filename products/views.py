from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from accounts.models import UserProfile
from accounts.permissions import IsAdminOrReadOnly

from .models import Category, Product
from .pagination import CustomPagination
from .serializers import CategorySerializer, ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer
    pagination_class = CustomPagination
    permission_classes = [IsAdminOrReadOnly]

    filter_backends = [SearchFilter, DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["category", "is_active"]
    search_fields = ["name", "description", "sku"]
    ordering_fields = ["price", "name", "created_at"]

    def get_queryset(self):
        user = self.request.user
        is_admin = False

        if user.is_authenticated:
            is_admin = UserProfile.objects.filter(user=user, role=UserProfile.Role.ADMIN).exists()

        if is_admin:
            return Product.objects.all().order_by("id")

        return Product.objects.filter(is_active=True).order_by("id")


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
