import secrets
import string

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def generate_temp_password(length: int = 12) -> str:
    """Return a cryptographically secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Guarantee at least one character from each required class.
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def send_employee_credentials(employee_name: str, email: str, username: str, password: str, facility_name: str) -> None:
    """Send login credentials to a newly created employee via plain-text and HTML email."""
    subject = f"Welcome to {facility_name} — Your Afyora Login Credentials"
    
    text_content = (
        f"Dear {employee_name},\n\n"
        f"Your account on the Afyora Health Management System has been created.\n\n"
        f"  Facility : {facility_name}\n"
        f"  Username : {username}\n"
        f"  Password : {password}\n\n"
        "Please log in and change your password immediately.\n\n"
        "If you did not expect this email, please contact your facility administrator.\n\n"
        "Regards,\n"
        "Afyora HMS"
    )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 8px; border: 1px solid #e1e8ed; }}
            .header {{ font-size: 20px; font-weight: bold; color: #1e293b; margin-bottom: 20px; text-align: center; }}
            .box {{ background: #f8fafc; border: 1px dashed #cbd5e1; padding: 15px; border-radius: 6px; margin: 20px 0; }}
            .label {{ font-size: 13px; color: #64748b; font-weight: bold; text-transform: uppercase; }}
            .val {{ font-size: 16px; color: #0f172a; font-family: monospace; font-weight: bold; margin-bottom: 10px; }}
            .footer {{ font-size: 12px; color: #94a3b8; text-align: center; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">Welcome to Afyora HMS</div>
            <p>Dear <strong>{employee_name}</strong>,</p>
            <p>Your user account for <strong>{facility_name}</strong> has been successfully created. Here are your temporary login credentials:</p>
            <div class="box">
                <div class="label">Facility</div>
                <div class="val" style="font-family: inherit;">{facility_name}</div>
                <div class="label">Username / Email</div>
                <div class="val">{username}</div>
                <div class="label">Temporary Password</div>
                <div class="val">{password}</div>
            </div>
            <p>Please log in and update your password upon your first sign-in.</p>
            <div class="footer">
                If you did not expect this email, please contact your facility administrator immediately.<br>
                &copy; Afyora Health Management System
            </div>
        </div>
    </body>
    </html>
    """

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
