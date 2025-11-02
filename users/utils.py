# users/utils.py
from django.core.mail import send_mail
from django.utils import timezone

from django.conf import settings


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

import uuid
from django.conf import settings


def generate_secure_uuid():
    token = uuid.uuid4()
    return token
