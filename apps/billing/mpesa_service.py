import base64
import datetime
import logging
import os
import requests
from django.conf import settings
from .models import MpesaConfig

logger = logging.getLogger(__name__)

# System-level / Render M-Pesa credentials for facility subscription payments
DEFAULT_SANDBOX_SHORTCODE = (
    os.getenv('MPESA_SHORTCODE') or os.getenv('SYSTEM_MPESA_SHORTCODE') or getattr(settings, 'MPESA_SHORTCODE', '')
)
DEFAULT_SANDBOX_PASSKEY = (
    os.getenv('MPESA_PASSKEY') or os.getenv('SYSTEM_MPESA_PASSKEY') or getattr(settings, 'MPESA_PASSKEY', 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919')
)
DEFAULT_SANDBOX_CONSUMER_KEY = (
    os.getenv('MPESA_CONSUMER_KEY') or os.getenv('MPESA_SANDBOX_CONSUMER_KEY') or os.getenv('SYSTEM_MPESA_CONSUMER_KEY') or getattr(settings, 'MPESA_SANDBOX_CONSUMER_KEY', 'bV57BHXJLAh3wd74dP6qMM3qLJpOsvrJEugUGyWKmdeZkuub')
)
DEFAULT_SANDBOX_CONSUMER_SECRET = (
    os.getenv('MPESA_CONSUMER_SECRET') or os.getenv('MPESA_SANDBOX_CONSUMER_SECRET') or os.getenv('SYSTEM_MPESA_CONSUMER_SECRET') or getattr(settings, 'MPESA_SANDBOX_CONSUMER_SECRET', 'W5vtiUaDHGkeuHtzMMXZBz8U0Cm1y8JyvFlYfbuwYqcnGRM16TBvP8352LJ461NM')
)

DEFAULT_SANDBOX_ENVIRONMENT = (
    os.getenv('MPESA_ENVIRONMENT') or os.getenv('SYSTEM_MPESA_ENVIRONMENT') or getattr(settings, 'MPESA_ENVIRONMENT', 'sandbox')
)



def format_phone_number(phone: str) -> str:
    """
    Normalizes Kenyan phone numbers to the canonical format: 254XXXXXXXXX.
    Examples:
        0712345678 -> 254712345678
        0112345678 -> 254112345678
        +254712345678 -> 254712345678
        254712345678 -> 254712345678
    """
    if not phone:
        return ""
    clean = str(phone).strip().replace(" ", "").replace("-", "").replace("+", "")
    if clean.startswith("0") and len(clean) == 10:
        return "254" + clean[1:]
    if clean.startswith("254") and len(clean) == 12:
        return clean
    if len(clean) == 9 and (clean.startswith("7") or clean.startswith("1")):
        return "254" + clean
    return clean


def get_facility_mpesa_config(facility):
    """
    Retrieves or creates default MpesaConfig for a facility.
    """
    if not facility:
        return None
    config, _ = MpesaConfig.objects.get_or_create(
        facility=facility,
        defaults={
            'shortcode': DEFAULT_SANDBOX_SHORTCODE,
            'passkey': DEFAULT_SANDBOX_PASSKEY,
            'consumer_key': DEFAULT_SANDBOX_CONSUMER_KEY,
            'consumer_secret': DEFAULT_SANDBOX_CONSUMER_SECRET,
            'environment': 'sandbox',
            'transaction_type': 'CustomerPayBillOnline',
            'account_reference_prefix': 'AfyoraHMS',
        }
    )
    return config


def get_base_url(environment: str) -> str:
    if environment == 'production':
        return 'https://api.safaricom.co.ke'
    return 'https://sandbox.safaricom.co.ke'


def get_access_token(consumer_key: str, consumer_secret: str, environment: str = 'sandbox') -> str:
    """
    Fetches an OAuth access token from Safaricom Daraja API.
    """
    ck = consumer_key.strip() if consumer_key else DEFAULT_SANDBOX_CONSUMER_KEY
    cs = consumer_secret.strip() if consumer_secret else DEFAULT_SANDBOX_CONSUMER_SECRET

    url = f"{get_base_url(environment)}/oauth/v1/generate?grant_type=client_credentials"

    try:
        response = requests.get(url, auth=(ck, cs), timeout=15)
        response.raise_for_status()
        data = response.json()
        token = data.get('access_token')
        if not token:
            raise Exception("No access_token found in Daraja OAuth response.")
        return token
    except Exception as e:
        logger.error(f"Failed to fetch M-Pesa Access Token with configured keys: {e}")
        if environment == 'sandbox' and ck != DEFAULT_SANDBOX_CONSUMER_KEY:
            logger.info("Attempting fallback to default Safaricom sandbox consumer keys...")
            try:
                response = requests.get(url, auth=(DEFAULT_SANDBOX_CONSUMER_KEY, DEFAULT_SANDBOX_CONSUMER_SECRET), timeout=15)
                response.raise_for_status()
                data = response.json()
                token = data.get('access_token')
                if token:
                    return token
            except Exception as fe:
                logger.error(f"Sandbox fallback keys also failed: {fe}")
        raise Exception(f"M-Pesa Authentication Error: {str(e)}")



def send_stk_push(config: MpesaConfig, phone_number: str, amount: float, account_ref: str, callback_url: str):
    """
    Sends a Lipa Na M-Pesa Online (STK Push) request to the Daraja API.
    """
    formatted_phone = format_phone_number(phone_number)
    if not formatted_phone or len(formatted_phone) != 12:
        raise ValueError(f"Invalid M-Pesa phone number format: '{phone_number}'. Expected 254XXXXXXXXX.")

    shortcode = (config.shortcode if config else DEFAULT_SANDBOX_SHORTCODE).strip()
    passkey = (config.passkey if config else DEFAULT_SANDBOX_PASSKEY).strip()
    env = (config.environment if config else DEFAULT_SANDBOX_ENVIRONMENT).strip()
    raw_txn_type = (config.transaction_type if config else 'CustomerPayBillOnline').strip()
    if shortcode == DEFAULT_SANDBOX_SHORTCODE or shortcode == '':
        txn_type = 'CustomerPayBillOnline'
    elif raw_txn_type in ['BuyGoodsOnline', 'CustomerBuyGoodsOnline']:
        txn_type = 'CustomerBuyGoodsOnline'
    else:
        txn_type = 'CustomerPayBillOnline'

    ck = config.consumer_key if config else DEFAULT_SANDBOX_CONSUMER_KEY
    cs = config.consumer_secret if config else DEFAULT_SANDBOX_CONSUMER_SECRET
    token = get_access_token(ck, cs, env)




    # Generate Timestamp (YYYYMMDDHHMMSS)
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y%m%d%H%M%S')

    # Password = Base64(Shortcode + Passkey + Timestamp)
    password_str = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode('utf-8')


    endpoint = f"{get_base_url(env)}/mpesa/stkpush/v1/processrequest"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    # Integer amount required by M-Pesa STK push API
    int_amount = int(round(float(amount)))
    if int_amount < 1:
        int_amount = 1

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": txn_type,
        "Amount": int_amount,
        "PartyA": formatted_phone,
        "PartyB": shortcode,
        "PhoneNumber": formatted_phone,
        "CallBackURL": callback_url,
        "AccountReference": account_ref[:12] if account_ref else "AfyoraHMS",
        "TransactionDesc": f"Payment for {account_ref}"[:20]
    }

    logger.info(f"Initiating STK Push for {formatted_phone}, Amount: {int_amount}, Shortcode: {shortcode}")

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=20)
        data = res.json()
        logger.info(f"Daraja STK Push Response: {data}")

        # Check response
        response_code = str(data.get('ResponseCode', ''))
        if response_code == '0':
            return {
                'success': True,
                'checkout_request_id': data.get('CheckoutRequestID'),
                'merchant_request_id': data.get('MerchantRequestID'),
                'response_description': data.get('ResponseDescription', 'STK Push sent successfully'),
                'customer_message': data.get('CustomerMessage', 'Please check your phone and enter M-Pesa PIN.')
            }
        else:
            return {
                'success': False,
                'error': data.get('CustomerMessage') or data.get('errorMessage') or data.get('ResponseDescription') or 'Failed to initiate STK Push.'
            }
    except Exception as e:
        logger.error(f"Error calling Daraja STK Push: {e}")
        return {
            'success': False,
            'error': f"Connection error to M-Pesa gateway: {str(e)}"
        }


def query_stk_status_from_daraja(config: MpesaConfig, checkout_request_id: str):
    """
    Queries Safaricom Daraja STK Query API for payment status.
    """
    shortcode = (config.shortcode if config else DEFAULT_SANDBOX_SHORTCODE).strip()
    passkey = (config.passkey if config else DEFAULT_SANDBOX_PASSKEY).strip()
    env = (config.environment if config else DEFAULT_SANDBOX_ENVIRONMENT).strip()

    now = datetime.datetime.now()
    timestamp = now.strftime('%Y%m%d%H%M%S')
    password_str = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode('utf-8')

    ck = config.consumer_key if config else DEFAULT_SANDBOX_CONSUMER_KEY
    cs = config.consumer_secret if config else DEFAULT_SANDBOX_CONSUMER_SECRET
    token = get_access_token(ck, cs, env)
    endpoint = f"{get_base_url(env)}/mpesa/stkpushquery/v1/query"


    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id
    }

    try:
        res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        data = res.json()
        logger.info(f"Daraja STK Query Response for {checkout_request_id}: {data}")
        return data
    except Exception as e:
        logger.error(f"Error querying Daraja STK status: {e}")
        return None


def complete_subscription_payment(payment, receipt_number=None):
    from django.utils import timezone
    from datetime import timedelta
    from core.models import AuditLog

    payment.status = 'completed'
    if receipt_number:
        payment.notes = f"M-Pesa payment completed. Receipt: {receipt_number}"
    payment.save()

    facility = payment.facility
    today = timezone.now().date()
    days_to_add = 365 if payment.billing_cycle == 'yearly' else 30
    new_end_date = today + timedelta(days=days_to_add)

    facility.subscription_package = payment.package
    facility.subscription_billing_cycle = payment.billing_cycle
    facility.subscription_active = True
    facility.subscription_start_date = today
    facility.subscription_end_date = new_end_date
    facility.save()

    # Create Audit log
    AuditLog.objects.create(
        facility=facility,
        action='update',
        model_name='Facility',
        object_id=str(facility.id),
        description=f"Subscription upgrade to {payment.package} ({payment.billing_cycle}) confirmed via M-Pesa. Ref: {payment.transaction_reference}"
    )

