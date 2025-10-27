# users/serializers.py
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone

from .models import User, Role


class RegisterSerializer(serializers.ModelSerializer):
    """
    For student registration only.
    Admin registration is triggered by another admin.
    """

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'username', 'email')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        student_role = Role.objects.get(name='student')
        user = User(
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            username=validated_data['username'],
            email=validated_data['email'],
            role=student_role,
            is_active=False
        )
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role.name if user.role else None
        user.last_login = timezone.now()
        user.save()
        return token
