# users/serializers.py
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Group, Role, User, UserGroup


class RegisterSerializer(serializers.ModelSerializer):
    """
    For student registration only.
    Admin registration is triggered by another admin.
    """

    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "username", "email", "is_active", "date_joined", "last_login", "role_name")
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        student_role = Role.objects.get(name="student")
        user = User(
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            username=validated_data["username"],
            email=validated_data["email"],
            role=student_role,
            is_active=False,
        )
        user.save()
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role.name if user.role else None
        token["username"] = user.username
        token["email"] = user.email

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        user.last_login = timezone.now()
        user.save()
        return token


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        if len(attrs["new_password"]) < 8:
            raise serializers.ValidationError({"new_password": "Password must be at least 8 characters."})
        return attrs


class EmptySerializer(serializers.Serializer):
    """Placeholder serializer – we don't actually use serializers in this viewset."""

    pass


class GroupMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    joined_date = serializers.DateTimeField(source="joined_at", read_only=True)

    class Meta:
        model = UserGroup
        fields = ["user_id", "username", "joined_date", "is_admin"]


class GroupListSerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)
    members = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "members_count", "members"]

    def get_members(self, obj: Group):
        memberships = obj.members.all().order_by("user__username")
        return GroupMemberSerializer(memberships, many=True).data
