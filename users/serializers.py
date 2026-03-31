# users/serializers.py
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
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

    def validate_username(self, value):
        username = (value or "").strip()
        if len(username) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters.")
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("This username is already in use.")
        return username

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("This email is already in use.")
        return email

    def validate_first_name(self, value):
        first_name = (value or "").strip()
        if not first_name:
            raise serializers.ValidationError("First name is required.")
        return first_name

    def validate_last_name(self, value):
        last_name = (value or "").strip()
        if not last_name:
            raise serializers.ValidationError("Last name is required.")
        return last_name

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
        try:
            user.save()
        except IntegrityError as exc:
            raise serializers.ValidationError({"detail": "Unable to create the account with the provided details."}) from exc
        return user


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # add identifier (email or username) as an input field
        self.fields["identifier"] = serializers.CharField()
        # remove the default username field so API only shows identifier + password
        if self.username_field in self.fields:
            self.fields.pop(self.username_field)

    def validate(self, attrs):
        identifier = attrs.get("identifier")
        password = attrs.get("password")

        user = (
            User.objects.filter(username__iexact=identifier).first()
            or User.objects.filter(email__iexact=identifier).first()
        )

        if not user or not user.check_password(password):
            raise serializers.ValidationError("No active account found with the given credentials")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")

        self.user = user

        data = super().validate({self.username_field: user.get_username(), "password": password})

        data["role"] = user.role.name if getattr(user, "role", None) else None
        data["username"] = user.username
        data["email"] = user.email
        return data

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
        validate_password(attrs["new_password"])
        return attrs


class SetPasswordWithTokenSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, required=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        validate_password(attrs["password"])
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
