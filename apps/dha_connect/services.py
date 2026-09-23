import os
import uuid
import datetime
import logging
import requests
from django.conf import settings
from .models import InsuranceProvider, DHALog

logger = logging.getLogger(__name__)


class DHAAfyaConnectClient:
    """
    Secure HTTP Client & Integration Gateway for DHA AfyaConnect ILM Middleware
    (https://ilm-dev.dha.go.ke/uat-middleware)
    """

    DEFAULT_BASE_URL = getattr(settings, 'DHA_BASE_URL', 'https://ilm-dev.dha.go.ke/uat-middleware')
    DEFAULT_TOKEN = getattr(settings, 'DHA_BEARER_TOKEN', 'dha_uat_secure_token_2026')

    def __init__(self, provider_code='SHA'):
        self.provider_code = provider_code
        self.base_url = self.DEFAULT_BASE_URL.rstrip('/')
        self.token = self.DEFAULT_TOKEN

        # Load provider credentials dynamically from InsuranceProvider DB model if configured
        try:
            provider = InsuranceProvider.objects.filter(code=provider_code, is_active=True).first()
            if not provider:
                provider = InsuranceProvider.objects.filter(is_active=True).first()

            if provider:
                if provider.gateway_url:
                    self.base_url = provider.gateway_url.rstrip('/')
                if provider.api_token:
                    self.token = provider.api_token
        except Exception as e:
            logger.warning(f"Using default DHA configuration due to DB error: {str(e)}")

    def _get_headers(self):
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        if self.token:
            headers['Authorization'] = f"Bearer {self.token}"
        return headers

    def _mask_payload(self, data):
        """Sanitize sensitive security data for audit logging."""
        if not isinstance(data, dict):
            return data
        sanitized = data.copy()
        sensitive_keys = ['otp', 'token', 'api_token', 'password', 'secret', 'ekycToken']
        for key in sensitive_keys:
            if key in sanitized and isinstance(sanitized[key], str):
                sanitized[key] = f"***MASKED-{sanitized[key][-3:] if len(sanitized[key]) > 3 else '***'}***"
        return sanitized

    def _log_communication(self, endpoint, method, status_code, req_payload, resp_payload, error_msg=None, is_mocked=False):
        """Save security audit record into DHALog."""
        try:
            DHALog.objects.create(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                request_payload=self._mask_payload(req_payload) if isinstance(req_payload, dict) else {},
                response_payload=self._mask_payload(resp_payload) if isinstance(resp_payload, dict) else {},
                error_message=error_msg,
                is_mocked=is_mocked,
            )
        except Exception as err:
            logger.error(f"Failed to log DHA communication: {str(err)}")

    def request(self, method, endpoint_path, params=None, json_data=None, files=None):
        """
        Execute live request against upstream DHA AfyaConnect Middleware Gateway.
        """
        url = f"{self.base_url}/{endpoint_path.lstrip('/')}"
        headers = self._get_headers()
        if files:
            # Drop Content-Type header to allow requests to calculate boundary for multipart uploads
            headers.pop('Content-Type', None)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                files=files,
                timeout=15
            )

            try:
                resp_data = response.json()
            except Exception:
                resp_data = {"message": response.text}

            self._log_communication(
                endpoint=endpoint_path,
                method=method,
                status_code=response.status_code,
                req_payload=json_data or params or {},
                resp_payload=resp_data,
                is_mocked=False
            )

            if response.status_code in [401, 403]:
                msg = resp_data.get('message') or resp_data.get('error') or 'DHA Gateway authorization failure'
                err_data = {
                    "error": True,
                    "message": f"DHA Gateway Authentication Error ({response.status_code}): {msg}",
                    "dha_status_code": response.status_code,
                    "details": resp_data
                }
                return err_data, 502

            return resp_data, response.status_code

        except (requests.exceptions.RequestException, Exception) as exc:
            logger.error(f"DHA API Communication Failure: {str(exc)}")
            err_data = {
                "error": True,
                "message": f"DHA AfyaConnect Gateway connection error: {str(exc)}",
                "status_code": 502
            }
            self._log_communication(
                endpoint=endpoint_path,
                method=method,
                status_code=502,
                req_payload=json_data or params or {},
                resp_payload=err_data,
                error_msg=str(exc),
                is_mocked=False
            )
            return err_data, 502
