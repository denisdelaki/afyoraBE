# apps/core/utils.py

import secrets
import string
import threading
import logging
from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from .models import EmailOTP

logger = logging.getLogger(__name__)


def generate_otp_code(length: int = 6) -> str:
    """Generate a cryptographically secure 6-digit OTP code."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def generate_and_send_otp(user, email: str = None) -> EmailOTP:
    """
    Generate a 6-digit OTP code valid for 1 hour, save to database,
    and send to user's email.
    """
    target_email = email or user.email
    code = generate_otp_code(6)
    expires_at = timezone.now() + timedelta(hours=1)

    # Invalidate existing active OTPs for this user
    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    # Create new OTP record
    otp_instance = EmailOTP.objects.create(
        user=user,
        email=target_email,
        code=code,
        expires_at=expires_at,
        is_used=False
    )

    # Send verification email
    subject = "Afyora HMS — Your Email Verification Code"

    text_content = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"Thank you for registering with Afyora Health Management System.\n\n"
        f"Your email verification code is: {code}\n\n"
        f"This verification code is valid for 1 hour (expires at {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}).\n"
        "If you did not request this code, please ignore this email.\n\n"
        "Regards,\n"
        "Afyora HMS Team"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 8px; border: 1px solid #e1e8ed; }}
            .header {{ font-size: 22px; font-weight: bold; color: #1e293b; margin-bottom: 20px; text-align: center; }}
            .otp-box {{ background: #f0fdf4; border: 2px dashed #22c55e; padding: 20px; border-radius: 8px; text-align: center; margin: 25px 0; }}
            .otp-code {{ font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #15803d; font-family: monospace; }}
            .expiry {{ font-size: 13px; color: #64748b; margin-top: 10px; }}
            .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 30px; border-top: 1px solid #f1f5f9; padding-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">Email Verification Code</div>
            <p>Dear <strong>{user.get_full_name() or user.username}</strong>,</p>
            <p>Thank you for signing up for Afyora HMS. Please use the verification code below to verify your email address and continue onboarding:</p>
            <div class="otp-box">
                <div class="otp-code">{code}</div>
                <div class="expiry">This code will expire in <strong>1 hour</strong>.</div>
            </div>
            <p>If you did not initiate this request, please disregard this message.</p>
            <div class="footer">
                &copy; Afyora Health Management System. All rights reserved.
            </div>
        </div>
    </body>
    </html>
    """

    def _send_email():
        import traceback
        import sys
        logger.debug(
            f"[OTP] Attempting email to {target_email} via "
            f"{settings.EMAIL_BACKEND} / {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
            f"(user={settings.EMAIL_HOST_USER})"
        )
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[target_email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            logger.info(f"[OTP] Email sent successfully to {target_email}")
            print(f"[OTP] Email sent successfully to {target_email}", flush=True)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[OTP] Failed to send email to {target_email}: {e}\n{tb}")
            # Also print to stderr as a guaranteed fallback visible in server console
            print(f"[OTP] EMAIL ERROR to {target_email}: {e}\n{tb}", file=sys.stderr, flush=True)

    # Send in a background thread so the request is NOT blocked by SMTP I/O.
    # daemon=True ensures the thread won't prevent the process from shutting down.
    email_thread = threading.Thread(target=_send_email, daemon=True)
    email_thread.start()

    return otp_instance
