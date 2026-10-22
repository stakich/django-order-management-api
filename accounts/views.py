from django.shortcuts import render
from rest_framework import generics
from .serializers import RegistrationSerializer, UserSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated


# Create your views here.

class RegisterView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]


class MeView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user