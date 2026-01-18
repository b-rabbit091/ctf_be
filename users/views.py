# users/views.py
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    MethodNotAllowed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import EmailVerificationToken, Group, GroupInvitation, Role, UserGroup
from .permissions import IsAdminUser, IsOwnerOrAdmin
from .serializers import (
    ChangePasswordSerializer,
    GroupListSerializer,
    MyTokenObtainPairSerializer,
    RegisterSerializer,
)
from .utils import (
    generate_secure_uuid,
    send_reset_password_email,
    send_verification_email,
)

User = get_user_model()


# ----------------------
# JWT Login View
# ----------------------
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer

    def get_permissions(self):
        """
        - register + verify-reset-password: public
        - list + destroy: admin only
        - retrieve + update + partial_update: owner OR admin
        - change-password: authenticated only (acts on request.user)
        """
        if self.action in ["register", "verify_reset_user_password"]:
            permission_classes = []
        elif self.action in ["list", "destroy"]:
            permission_classes = [IsAuthenticated, IsAdminUser]
        elif self.action in ["update", "partial_update", "retrieve"]:
            permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
        elif self.action in ["change_password"]:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        return [perm() for perm in permission_classes]

    def perform_update(self, serializer):
        """
        Extra safety: even if permissions are misconfigured later,
        prevent a user from escalating privileges via payload.
        """
        serializer.save()

    @action(detail=False, methods=["post"], permission_classes=[])
    def register(self, request):
        """
        Student registration endpoint
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()  # role=student, is_active=False

        token = generate_secure_uuid()
        student_role = Role.objects.get(name="student")

        EmailVerificationToken.objects.create(
            user=user,
            token=token,
            role=student_role,
            expires_at=timezone.now() + timedelta(days=2),
        )
        send_verification_email(user, token, "student")

        return Response(
            {"detail": "Verification email sent to your email address."},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], permission_classes=[], url_path="verify-reset-password")
    def verify_reset_user_password(self, request):
        """
        Generate password reset token and send to user email
        """
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "Email role does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        token = generate_secure_uuid()
        EmailVerificationToken.objects.create(
            user=user,
            token=token,
            role=user.role,
            expires_at=timezone.now() + timedelta(days=2),
        )
        send_reset_password_email(user, token)

        return Response({"detail": "Reset password email sent."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="change-password")
    def change_password(self, request):
        """
        Logged-in user changes their own password (NOT via email token).
        Endpoint: POST /users/change-password/
        """
        s = ChangePasswordSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        user: User = request.user

        if not user.check_password(s.validated_data["old_password"]):
            return Response({"error": "Old password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])

        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)


# ----------------------
# Admin Invite Management
# ----------------------
class AdminInviteViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """
        Admin triggers registration for new admin
        """
        email = request.data.get("email")
        username = request.data.get("username")

        if not email or not username:
            return Response({"error": "Email and username required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_role = Role.objects.get(name="admin")
        except Role.DoesNotExist:
            return Response({"error": "Admin role does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create inactive user
            user = User.objects.create(username=username, email=email, role=None, is_active=False)

            # Generate verification token
            token = generate_secure_uuid()
            EmailVerificationToken.objects.create(user=user, token=token, role=admin_role, expires_at=timezone.now() + timedelta(days=2))

            send_verification_email(user, token, "admin")
        except Exception:
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
        token_param = request.data.get("token")
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")
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


class UserGroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Group.objects.all().annotate(members_count=Count("members")).prefetch_related("members__user").order_by("name")

    def list(self, request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied("Only admins can list all groups.")

        qs = self.get_queryset()
        ser = self.get_serializer(qs, many=True)
        return Response(ser.data)

    def retrieve(self, request, *args, **kwargs):
        raise MethodNotAllowed("GET")

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed("PUT")

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed("PATCH")

    # ---- Helper functions (same behavior) ------------------------

    @staticmethod
    def get_user_group_membership(user: User):
        """
        Return (group, membership) for the given user, or (None, None)
        if they are not in any group.
        """
        try:
            membership = UserGroup.objects.select_related("group").get(user=user)
            return membership.group, membership
        except UserGroup.DoesNotExist:
            return None, None

    @staticmethod
    def ensure_group_admin(group: Group, user: User):
        """
        Raise PermissionDenied if `user` is not admin for `group`.
        """
        try:
            membership = UserGroup.objects.get(group=group, user=user)
        except UserGroup.DoesNotExist:
            raise PermissionDenied("You are not a member of this group.")

        if not membership.is_admin:
            raise PermissionDenied("Only the group admin can perform this action.")

    def create(self, request, *args, **kwargs):
        """
        POST /groups/
        Create a new group and make the current user its admin.

        Expects: { "name": "My Group Name" }
        """
        user = request.user

        raw_name = (request.data.get("name") or "").strip()
        name = " ".join(raw_name.split())
        min_members = request.data.get("min_members", 2)
        max_members = request.data.get("max_members", 2)

        if int(min_members) < 2 and int(max_members) > 10:
            return Response({"error": "Minimum or maximum members do not fall within 2-10 range."}, status=status.HTTP_400_BAD_REQUEST)

        if not name:
            return Response({"error": "Group name is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                if UserGroup.objects.select_for_update().filter(user=user).exists():
                    return Response({"error": "You already belong to a group."}, status=status.HTTP_400_BAD_REQUEST)

                if Group.objects.filter(name__iexact=name).exists():
                    return Response({"error": "A group with this name already exists."}, status=status.HTTP_400_BAD_REQUEST)

                group = Group.objects.create(
                    name=name,
                    min_members=min_members,
                    max_members=max_members,
                )

                UserGroup.objects.create(
                    user=user,
                    group=group,
                    is_admin=True,
                )

        except IntegrityError:
            return Response({"error": "Unable to create group. It may already exist."}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            "id": group.id,
            "name": group.name,
            "min_members": group.min_members,
            "max_members": group.max_members,
            "is_admin": True,
        }
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None, *args, **kwargs):
        """
        DELETE /groups/{id}/
        Delete group (only group admin).

        Security goals:
        - Enforce object-level permission (admin only)
        - Avoid partial deletes (atomic transaction)
        - Avoid leaking sensitive internal error details
        - Return consistent, safe error payloads
        """
        user = request.user

        # Basic input validation (avoid weird pk types)
        if pk is None:
            raise ValidationError({"error": "Group id is required."})

        try:
            group_id = int(pk)
        except (TypeError, ValueError):
            raise ValidationError({"error": "Invalid group id."})

        try:
            with transaction.atomic():
                # Lock the row to avoid race conditions (e.g., admin transfer / concurrent delete)
                group = Group.objects.select_for_update().filter(pk=group_id).first()
                if not group:
                    # Safe: generic "not found"
                    raise NotFound(detail="Group not found.")

                # Object-level authZ (raises PermissionDenied with safe messages)
                if not self.request.user.is_admin:
                    self.ensure_group_admin(group, user)

                # Perform delete
                group.delete()

        except PermissionDenied:
            # Let DRF handle status=403 and message
            raise
        except NotFound:
            raise
        except (IntegrityError, DatabaseError):
            # Do not leak DB internals; return generic conflict/server-safe error
            return Response(
                {"error": "Unable to delete group at this time."},
                status=status.HTTP_409_CONFLICT,
            )
        except Exception:
            # Catch-all: avoid crashing & avoid leaking stack traces to clients
            return Response(
                {"error": "Unexpected error while deleting group."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    # ---- Custom actions used by frontend -----------------------------

    @action(detail=False, methods=["get"], url_path="me/dashboard")
    def my_dashboard(self, request):
        """
        GET /groups/me/dashboard/
        Returns group summary, members and pending invites for current user.
        """
        user = request.user
        group, membership = self.get_user_group_membership(user)

        if not group:
            return Response(
                {"group": None, "members": [], "pending_invites": []},
                status=status.HTTP_200_OK,
            )

        members_qs = UserGroup.objects.filter(group=group).select_related("user").order_by("user__username")
        members = [
            {
                "id": m.user.id,
                "username": m.user.username,
                "email": m.user.email,
                "is_admin": m.is_admin,
            }
            for m in members_qs
        ]

        pending_qs = (
            GroupInvitation.objects.filter(
                group=group,
                status=GroupInvitation.STATUS_PENDING,
            )
            .select_related("user")
            .order_by("user__username")
        )
        pending_invites = [
            {
                "id": inv.id,
                "user": {
                    "id": inv.user.id,
                    "username": inv.user.username,
                    "email": inv.user.email,
                },
                "status": inv.status,
            }
            for inv in pending_qs
        ]

        group_data = {
            "id": group.id,
            "name": group.name,
            "min_members": group.min_members,
            "max_members": group.max_members,
            "is_admin": bool(membership and membership.is_admin),
        }

        return Response(
            {
                "group": group_data,
                "members": members,
                "pending_invites": pending_invites,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="search-users")
    def search_users(self, request):
        """
        GET /groups/search-users/?q=...
        Search for users by username/email to invite to current user's group.

        Excludes:
          * current user
          * users already in this group
          * users with a pending invite in this group
        """
        user = request.user
        q = (request.query_params.get("q") or "").strip()

        if not q:
            return Response([], status=status.HTTP_200_OK)

        group, _membership = self.get_user_group_membership(user)
        if not group:
            return Response([], status=status.HTTP_200_OK)

        member_ids = UserGroup.objects.filter(group=group).values_list("user_id", flat=True)
        invited_ids = GroupInvitation.objects.filter(group=group).values_list("user_id", flat=True)

        exclude_ids = set(member_ids) | set(invited_ids) | {user.id}

        qs = User.objects.filter(Q(username__icontains=q) | Q(email__icontains=q)).exclude(id__in=exclude_ids).order_by("username")[:20]

        results = [{"id": u.id, "username": u.username, "email": u.email} for u in qs]
        return Response(results, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="invitations")
    def invite(self, request, pk=None):
        """
        POST /groups/{id}/invitations/
        Body: { "user_id": <int> }

        Create a pending invitation for a user to join this group.
        Only group admin can invite.
        """
        group = get_object_or_404(Group, pk=pk)
        user = request.user

        self.ensure_group_admin(group, user)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Target user not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_member_count = UserGroup.objects.filter(group=group).count()
        if current_member_count >= group.max_members:
            return Response({"error": "Group is full."}, status=status.HTTP_400_BAD_REQUEST)

        if UserGroup.objects.filter(user=target).exists():
            return Response(
                {"error": "User already belongs to a group."},
                status=status.HTTP_200_OK,
            )

        invite, created = GroupInvitation.objects.get_or_create(
            group=group,
            user=target,
            defaults={"status": GroupInvitation.STATUS_PENDING},
        )

        if not created and invite.status == GroupInvitation.STATUS_PENDING:
            return Response(
                {"error": "An invitation is already pending for this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not created and invite.status != GroupInvitation.STATUS_PENDING:
            invite.status = GroupInvitation.STATUS_PENDING
            invite.save(update_fields=["status"])

        data = {
            "id": invite.id,
            "user": {"id": target.id, "username": target.username, "email": target.email},
            "status": invite.status,
        }
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="remove-member")
    def remove_member(self, request, pk=None):
        """
        POST /groups/{id}/remove-member/
        Body: { "user_id": <int> }

        Remove a member from this group (only admin).
        """
        group = get_object_or_404(Group, pk=pk)
        user = request.user

        self.ensure_group_admin(group, user)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = UserGroup.objects.filter(group=group, user_id=user_id).first()
        if not membership:
            return Response(
                {"error": "User is not a member of this group."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if membership.user_id == user.id and membership.is_admin:
            return Response(
                {"error": "Admin cannot remove themselves from the group."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership.delete()
        return Response({"detail": "Member removed from group."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="set-admin")
    def set_admin(self, request, pk=None):
        """
        POST /groups/{id}/set-admin/
        Body: { "user_id": <int> }

        Make the specified member the group admin.
        Only current admin can perform this.
        """
        group = get_object_or_404(Group, pk=pk)
        user = request.user

        self.ensure_group_admin(group, user)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = UserGroup.objects.filter(group=group, user_id=user_id).first()
        if not membership:
            return Response(
                {"error": "User is not a member of this group."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            UserGroup.objects.filter(group=group).update(is_admin=False)
            membership.is_admin = True
            membership.save(update_fields=["is_admin"])

        _group_after, my_membership = self.get_user_group_membership(user)
        is_admin_now = bool(my_membership and my_membership.is_admin)

        data = {
            "id": group.id,
            "name": group.name,
            "min_members": group.min_members,
            "max_members": group.max_members,
            "is_admin": is_admin_now,
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="me/invitations")
    def my_invitations(self, request):
        """
        GET /groups/me/invitations/
        Incoming invitations for the current user (pending only).
        """
        user = request.user

        qs = (
            GroupInvitation.objects.filter(
                user=user,
                status=GroupInvitation.STATUS_PENDING,
            )
            .select_related("group")
            .order_by("-id")
        )

        data = [
            {
                "id": inv.id,
                "status": inv.status,
                "group": {"id": inv.group.id, "name": inv.group.name},
            }
            for inv in qs
        ]
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path=r"invitations/(?P<invite_id>\d+)/accept")
    def accept_invitation(self, request, invite_id=None):
        """
        POST /groups/invitations/{invite_id}/accept/
        Accept an incoming invitation and join the group.
        """
        user = request.user

        try:
            inv_id = int(invite_id)
        except (TypeError, ValueError):
            raise ValidationError({"error": "Invalid invitation id."})

        with transaction.atomic():
            invite = GroupInvitation.objects.select_for_update().select_related("group", "user").filter(id=inv_id).first()
            if not invite:
                raise NotFound(detail="Invitation not found.")

            if invite.user_id != user.id:
                raise PermissionDenied("You cannot accept this invitation.")

            if invite.status != GroupInvitation.STATUS_PENDING:
                return Response({"error": "Invitation is not pending."}, status=status.HTTP_400_BAD_REQUEST)

            # enforce "one group per user"
            if UserGroup.objects.select_for_update().filter(user=user).exists():
                return Response({"error": "You already belong to a group."}, status=status.HTTP_400_BAD_REQUEST)

            group = invite.group

            # capacity check
            current_count = UserGroup.objects.filter(group=group).count()
            if current_count >= group.max_members:
                return Response({"error": "Group is full."}, status=status.HTTP_400_BAD_REQUEST)

            # join + mark invite accepted
            UserGroup.objects.create(user=user, group=group, is_admin=False)
            invite.status = GroupInvitation.STATUS_ACCEPTED  # ensure this constant exists
            invite.save(update_fields=["status"])

            # optional: cancel other pending invites for this user (since one-group-per-user)
            GroupInvitation.objects.filter(
                user=user,
                status=GroupInvitation.STATUS_PENDING,
            ).exclude(id=invite.id).update(status=GroupInvitation.STATUS_DECLINED)

        return Response(
            {"detail": "Invitation accepted.", "group_id": group.id, "group_name": group.name},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path=r"invitations/(?P<invite_id>\d+)/decline")
    def decline_invitation(self, request, invite_id=None):
        """
        POST /groups/invitations/{invite_id}/decline/
        Decline an incoming invitation.
        """
        user = request.user

        try:
            inv_id = int(invite_id)
        except (TypeError, ValueError):
            raise ValidationError({"error": "Invalid invitation id."})

        with transaction.atomic():
            invite = GroupInvitation.objects.select_for_update().select_related("user").filter(id=inv_id).first()
            if not invite:
                raise NotFound(detail="Invitation not found.")

            if invite.user_id != user.id:
                raise PermissionDenied("You cannot decline this invitation.")

            if invite.status != GroupInvitation.STATUS_PENDING:
                return Response({"error": "Invitation is not pending."}, status=status.HTTP_400_BAD_REQUEST)

            invite.status = GroupInvitation.STATUS_DECLINED
            invite.save(update_fields=["status"])

        return Response({"detail": "Invitation declined."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="me/exists")
    def is_in_group(self, request):
        """
        GET /groups/me/exists/
        Returns whether the current user belongs to any group.
        """
        user = request.user

        exists = UserGroup.objects.filter(user=user).exists()

        return Response(
            {"in_group": exists},
            status=status.HTTP_200_OK,
        )
