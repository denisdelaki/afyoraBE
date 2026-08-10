import secrets
import string

from django.conf import settings
from django.core.mail import send_mail


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
    """Send login credentials to a newly created employee."""
    subject = f"Welcome to {facility_name} — Your Afyora Login Credentials"
    body = (
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
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
