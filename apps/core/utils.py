# apps/core/utils.py

import secrets
import string
import threading
import logging
from datetime import timedelta
from email.utils import parseaddr
import requests
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from .models import EmailOTP

logger = logging.getLogger(__name__)


# ============================================================================
# RBAC PERMISSION HELPER
# ============================================================================

def check_module_permission(user, module_key: str) -> None:
    """
    Raise PermissionDenied if the user lacks access to the given module.

    Logic:
    1. facility_admin and admin always have full access.
    2. If the user has a custom_role with a permissions map, evaluate that.
    3. If the user has no custom_role, fall back to static role-based defaults.

    Raises PermissionDenied if access is denied.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        raise PermissionDenied('Authentication required.')

    static_role = getattr(user, 'role', 'staff')

    # Admins and facility admins always pass.
    if static_role in ('admin', 'facility_admin'):
        return

    # Check dynamic custom role permissions first.
    custom_role = getattr(user, 'custom_role', None)
    if custom_role is not None:
        perms = getattr(custom_role, 'permissions', {}) or {}
        if perms.get(module_key, False):
            return
        raise PermissionDenied(
            f'Your role "{custom_role.name}" does not have access to the {module_key} module.'
        )

    # Fallback: static role defaults (mirrors frontend ROLE_PROFILES).
    STATIC_ROLE_PERMISSIONS: dict[str, set] = {
        'doctor':        {'patients', 'appointments', 'laboratory', 'ehr', 'visit_queue'},
        'nurse':         {'patients', 'appointments', 'ehr', 'visit_queue'},
        'receptionist':  {'patients', 'appointments', 'visit_queue'},
        'pharmacist':    {'pharmacy', 'inventory'},
        'lab_technician':{'laboratory', 'patients'},
        'radiologist':   {'radiology', 'patients'},
        'accountant':    {'billing', 'reports'},
        'hr':            {'employees', 'departments'},
        'manager':       {
            'patients', 'appointments', 'laboratory', 'pharmacy',
            'radiology', 'billing', 'inventory', 'reports',
            'employees', 'departments', 'ehr', 'visit_queue',
            'dashboard_overview',
        },
        'staff':         set(),
    }

    allowed = STATIC_ROLE_PERMISSIONS.get(static_role, set())
    if module_key in allowed:
        return

    raise PermissionDenied(
        f'Your role "{static_role}" does not have access to the {module_key} module.'
    )


def send_transactional_email(*, to_email: str, subject: str, text: str, html: str) -> str:
    """Send an email through Brevo's HTTPS transactional email API."""
    api_key = settings.BREVO_API_KEY
    if not api_key:
        raise RuntimeError('BREVO_API_KEY is not configured.')

    sender_name, sender_email = parseaddr(settings.DEFAULT_FROM_EMAIL)
    if not sender_email:
        raise RuntimeError('DEFAULT_FROM_EMAIL must contain a valid sender email address.')

    sender = {'email': sender_email}
    if sender_name:
        sender['name'] = sender_name

    response = requests.post(
        settings.BREVO_API_URL,
        headers={
            'api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        json={
            'sender': sender,
            'to': [{'email': to_email}],
            'subject': subject,
            'textContent': text,
            'htmlContent': html,
        },
        timeout=settings.BREVO_TIMEOUT,
    )
    if not response.ok:
        logger.error(
            '[OTP] Brevo API error %s for %s: %s',
            response.status_code, to_email, response.text,
        )
    response.raise_for_status()
    return response.json().get('messageId', '')

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
        logger.debug('[OTP] Attempting transactional API email to %s', target_email)
        try:
            message_id = send_transactional_email(
                to_email=target_email,
                subject=subject,
                text=text_content,
                html=html_content,
            )
            logger.info('[OTP] Email sent successfully to %s (provider_id=%s)', target_email, message_id)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[OTP] Failed to send email to {target_email}: {e}\n{tb}")
            print(f"[OTP] EMAIL ERROR to {target_email}: {e}\n{tb}", file=sys.stderr, flush=True)

    # Send in a background thread so the request is NOT blocked by HTTP I/O.
    # daemon=True ensures the thread won't prevent the process from shutting down.
    email_thread = threading.Thread(target=_send_email, daemon=True)
    email_thread.start()

    return otp_instance
