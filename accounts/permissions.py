from rest_framework import permissions
from .models import UserProfile


class IsAdminRole(permissions.BasePermission):

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        return UserProfile.objects.filter(
            user=request.user,
            role=UserProfile.Role.ADMIN
        ).exists()


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        if not request.user.is_authenticated:
            return False

        return UserProfile.objects.filter(
            user=request.user,
            role=UserProfile.Role.ADMIN
        ).exists()
