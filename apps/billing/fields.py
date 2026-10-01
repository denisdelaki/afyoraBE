import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


ENCRYPTED_PREFIX = 'enc::'


def get_mpesa_fernet():
    encryption_key = settings.MPESA_CREDENTIAL_ENCRYPTION_KEY
    if not encryption_key:
        raise ImproperlyConfigured('MPESA_CREDENTIAL_ENCRYPTION_KEY is not configured.')
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(encryption_key.encode()).digest())
    return Fernet(derived_key)


def encrypt_mpesa_secret(value):
    if not value or value.startswith(ENCRYPTED_PREFIX):
        return value
    token = get_mpesa_fernet().encrypt(value.encode()).decode()
    return f'{ENCRYPTED_PREFIX}{token}'


def decrypt_mpesa_secret(value):
    if not value or not value.startswith(ENCRYPTED_PREFIX):
        return value
    try:
        return get_mpesa_fernet().decrypt(value[len(ENCRYPTED_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            'Unable to decrypt M-Pesa credentials. Check MPESA_CREDENTIAL_ENCRYPTION_KEY.'
        ) from exc


class EncryptedTextField(models.CharField):
    def from_db_value(self, value, expression, connection):
        return decrypt_mpesa_secret(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_mpesa_secret(value)