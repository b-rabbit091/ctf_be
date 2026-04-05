# users/utils.py
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import parseaddr
from smtplib import SMTPException

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response

from users.models import Group, UserGroup

User = get_user_model()


class EmailDeliveryError(Exception):
    pass


def _send_platform_email(subject: str, message: str, recipient_list: list[str]) -> None:
    from_email = parseaddr(settings.DEFAULT_FROM_EMAIL)[1] or settings.DEFAULT_FROM_EMAIL
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.DEFAULT_FROM_EMAIL
    msg["To"] = ", ".join(recipient_list)
    msg.set_content(message)

    server = None
    try:
        if settings.EMAIL_USE_SSL:
            server = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=15)
        else:
            server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=15)

        server.send_message(msg, from_addr=from_email, to_addrs=recipient_list)
    except Exception as exc:
        if isinstance(exc, SMTPException):
            raise EmailDeliveryError(f"Unable to deliver email right now. SMTP error: {exc}") from exc
        raise EmailDeliveryError(f"Unable to deliver email right now. Error: {exc}") from exc
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


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
    _send_platform_email(subject, message, [user.email])


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
    _send_platform_email(subject, message, [user.email])


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
