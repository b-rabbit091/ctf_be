# users/utils.py
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework import status
from rest_framework.response import Response

from users.models import Group, UserGroup

User = get_user_model()


def send_verification_email(user, token, role_name):
    """
    Sends a verification email to the user.
    The link contains the token and backend determines the role.
    """
    verification_link = f"{settings.BASE_URL}/verify-email?token={token}"

    subject = "CTF Platform Email Verification"
    message = f"""
Hello {user.username},

Please verify your email and set your password by clicking the link below:

{verification_link}

This link is valid for 48 hours.

Role assigned: {role_name.capitalize()}
"""
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]

    send_mail(
        subject,
        message,
        from_email,
        recipient_list,
        fail_silently=False,
    )


def send_reset_password_email(user, token):
    """
    Sends a verification email to the user.
    The link contains the token and backend determines the role.
    """
    verification_link = f"{settings.BASE_URL}/reset-password?token={token}"

    subject = "CTF Platform Password Reset"
    message = f"""
Hello {user.username},

Please set your password by clicking the link below:

{verification_link}

This link is valid for 48 hours.
"""
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]
    send_mail(
        subject,
        message,
        from_email,
        recipient_list,
        fail_silently=False,
    )


def generate_secure_uuid():
    token = uuid.uuid4()
    return token


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


def ensure_group_admin(group: Group, user: User):
    """
    Raise PermissionDenied if `user` is not admin for `group`.
    """
    try:
        membership = UserGroup.objects.get(group=group, user=user)
    except UserGroup.DoesNotExist:
        return Response(
            {"detail": "You are not a member of this group."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        # raise PermissionDenied("You are not a member of this group.")

    if not membership.is_admin:
        return Response(
            {"detail": "Only the group admin can perform this action."},
            status=status.HTTP_403_FORBIDDEN,
        )
        # raise PermissionDenied("Only the group admin can perform this action.")

    return True
