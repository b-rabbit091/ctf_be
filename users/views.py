# users/views.py
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, EmailVerificationToken
from .permissions import IsAdminUser, IsOwnerOrAdmin
from .serializers import RegisterSerializer, MyTokenObtainPairSerializer
from .utils import send_verification_email, generate_secure_uuid, send_reset_password_email

User = get_user_model()


# ----------------------
# JWT Login View
# ----------------------
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# ----------------------
# User Management
# ----------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_permissions(self):
        if self.action in ['list', 'destroy', 'update', 'partial_update']:
            permission_classes = [IsAuthenticated, IsAdminUser]
        elif self.action in ['register', 'verify_reset_user_password']:
            permission_classes = []
        else:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        return [perm() for perm in permission_classes]

    @action(detail=False, methods=['post'], permission_classes=[])
    def register(self, request):
        """
        Student registration endpoint
        """
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = serializer.save()  # creates user with is_active=False, role=student

            # Generate verification token
            token = generate_secure_uuid()
            student_role = Role.objects.get(name='student')

            EmailVerificationToken.objects.create(
                user=user,
                token=token,
                role=student_role,
                expires_at=timezone.now() + timedelta(days=2)
            )
            send_verification_email(user, token, 'student')

            return Response(
                {"detail": "Verification email sent to your email address."},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": "Error while registering student."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=['post'], permission_classes=[], url_path='verify-reset-password')
    def verify_reset_user_password(self, request):
        """
        Generate Password reset token and sent to user email
        """
        email = request.data.get('email')

        if not email:
            return Response({"error": "Email  required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "Email role does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:

            token = generate_secure_uuid()
            EmailVerificationToken.objects.create(
                user=user,
                token=token,
                role=user.role,
                expires_at=timezone.now() + timedelta(days=2)
            )
            send_reset_password_email(user, token)
        except Exception as e:
            return Response({"error": "Error while registering admin."}, status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Reset password email sent to the new admin."}, status=status.HTTP_200_OK)


# ----------------------
# Admin Invite Management
# ----------------------
class AdminInviteViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Admin triggers registration for new admin
        """
        email = request.data.get('email')
        username = request.data.get('username')

        if not email or not username:
            return Response({"error": "Email and username required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_role = Role.objects.get(name='admin')
        except Role.DoesNotExist:
            return Response({"error": "Admin role does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create inactive user
            user = User.objects.create(
                username=username,
                email=email,
                role=None,
                is_active=False
            )

            # Generate verification token
            token = generate_secure_uuid()
            EmailVerificationToken.objects.create(
                user=user,
                token=token,
                role=admin_role,
                expires_at=timezone.now() + timedelta(days=2)
            )

            # Send email with link (frontend URL placeholder)
            send_verification_email(user, token, 'admin')
        except Exception as e:
            return Response({"error": "Error while registering admin."}, status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Verification email sent to the new admin."}, status=status.HTTP_200_OK)


# ----------------------
# Email Verification + Set Password
# ----------------------
class VerifyEmailView(APIView):
    """
    Endpoint to verify email and set password.
    Works for both students and admin registrations.
    """
    permission_classes = []

    def post(self, request):
        token_param = request.data.get('token')
        password = request.data.get('password')
        confirm_password = request.data.get('confirm_password')
        if confirm_password != password:
            return Response({"error": "Passwords donot match."}, status.HTTP_400_BAD_REQUEST)

        if not token_param or not password:
            return Response({"error": "Token and password required"}, status.HTTP_400_BAD_REQUEST)

        try:
            token_obj = EmailVerificationToken.objects.get(token=token_param)
        except EmailVerificationToken.DoesNotExist:
            return Response({"error": "Invalid token"}, status.HTTP_400_BAD_REQUEST)

        if token_obj.expires_at < timezone.now():
            return Response({"error": "Token expired"}, status.HTTP_400_BAD_REQUEST)

        user = token_obj.user
        user.set_password(password)
        role = token_obj.role
        if not role:
            role = user.role
        user.role = role
        user.is_active = True
        user.save()

        token_obj.delete()

        return Response({"detail": "Password set successfully. You can now login."}, status=status.HTTP_201_CREATED)
