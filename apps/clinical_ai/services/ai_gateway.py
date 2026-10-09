import logging
import uuid
from typing import Literal
from urllib.parse import urlsplit

import requests
from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rest_framework.exceptions import APIException

logger = logging.getLogger('clinical_ai')

class ClinicalAIServiceError(APIException):
    def __init__(self, code, message, status_code=502, request_id=None, upstream_status=None, upstream_code=None):
        self.status_code = status_code
        self.request_id = request_id or str(uuid.uuid4())
        error = {'code': code, 'message': message}
        if upstream_status is not None:
            error['upstream_status'] = upstream_status
        if upstream_code is not None:
            error['upstream_code'] = upstream_code
        super().__init__({'error': error, 'request_id': self.request_id})


class AnalyzerTriage(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    level: Literal['routine', 'urgent', 'emergency']
    urgent_care_recommended: bool
    reasons: list[str]
    unassessed_vitals: list[str]
    recommendation: str
    requires_human_review: bool
    rule_set: str


class AnalyzerResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    supported_diagnosis: str
    possible_disease: list[str]
    drugs_admissible: list[str]
    further_labs_to_be_done: list[str]
    triage: AnalyzerTriage


def call_clinical_ai_analysis(payload: dict) -> dict:
    base_url = settings.CLINICAL_AI_BASE_URL.rstrip('/')
    token = settings.CLINICAL_AI_TOKEN
    request_id = str(uuid.uuid4())
    parsed_url = urlsplit(base_url)
    if not token or not parsed_url.hostname or parsed_url.scheme not in ('http', 'https'):
        raise ClinicalAIServiceError(
            'clinical_ai_not_configured', 'Clinical AI integration is not configured.', 503, request_id,
        )
    if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
        raise ClinicalAIServiceError(
            'clinical_ai_not_configured', 'Clinical AI base URL is invalid.', 503, request_id,
        )
    if parsed_url.scheme != 'https' and parsed_url.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ClinicalAIServiceError(
            'clinical_ai_not_configured', 'Clinical AI requires HTTPS outside local development.', 503, request_id,
        )
    try:
        response = requests.post(
            f'{base_url}/api/clinical-ai/analyze/',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Request-ID': request_id,
            },
            json=payload,
            timeout=settings.CLINICAL_AI_TIMEOUT,
            allow_redirects=False,
        )
    except requests.Timeout:
        raise ClinicalAIServiceError('clinical_ai_timeout', 'Clinical AI timed out.', 504, request_id) from None
    except requests.RequestException:
        raise ClinicalAIServiceError('clinical_ai_unreachable', 'Clinical AI is unreachable.', 502, request_id) from None
    if response.status_code != 200:
        logger.warning('Clinical AI request failed: status=%s request_id=%s', response.status_code, request_id)
        if response.status_code in (401, 403):
            raise ClinicalAIServiceError(
                'clinical_ai_authentication_failed', 'Clinical AI integration access must be configured by the operator.',
                503, request_id,
            )
        status_code = response.status_code if response.status_code in (400, 429, 502, 503, 504) else 502
        code, message = {
            400: ('clinical_ai_request_rejected', 'Standalone Clinical AI rejected the clinical request.'),
            429: ('clinical_ai_rate_limited', 'Standalone Clinical AI reported a provider rate limit.'),
            502: ('clinical_ai_provider_failure', 'Standalone Clinical AI reported a provider failure or invalid model response. Contact the service operator with the request ID.'),
            503: ('clinical_ai_provider_unavailable', 'Standalone Clinical AI reported that its provider is unavailable or not configured.'),
            504: ('clinical_ai_provider_timeout', 'Standalone Clinical AI reported a provider timeout.'),
        }.get(response.status_code, ('clinical_ai_request_failed', 'Standalone Clinical AI returned an unexpected HTTP status.'))
        upstream_code = None
        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get('error') if isinstance(body, dict) else None
        candidate_code = error.get('code') if isinstance(error, dict) else None
        known_errors = {
            'ai_provider_error': ('clinical_ai_provider_failure', 'The standalone AI provider request failed. Its operator should check Groq credentials, model access, and provider diagnostics.'),
            'ai_invalid_response': ('clinical_ai_invalid_model_response', 'The standalone AI provider returned output that failed its response schema validation.'),
            'ai_analysis_failed': ('clinical_ai_analysis_failed', 'Standalone Clinical AI encountered an internal analysis failure.'),
            'ai_provider_unavailable': ('clinical_ai_provider_unavailable', 'The standalone AI provider is unavailable or not configured.'),
            'ai_rate_limited': ('clinical_ai_rate_limited', 'The standalone AI provider is rate limited.'),
            'ai_timeout': ('clinical_ai_provider_timeout', 'The standalone AI provider timed out.'),
            'invalid_request': ('clinical_ai_request_rejected', 'Standalone Clinical AI rejected the clinical request.'),
        }
        if isinstance(candidate_code, str) and candidate_code in known_errors:
            upstream_code = candidate_code
            code, message = known_errors[candidate_code]
            logger.warning('Clinical AI error category=%s request_id=%s', upstream_code, request_id)
        raise ClinicalAIServiceError(
            code, message, status_code, request_id,
            upstream_status=response.status_code, upstream_code=upstream_code,
        )
    try:
        response_body = response.json()
    except ValueError:
        logger.warning('Clinical AI response was not valid JSON request_id=%s', request_id)
        raise ClinicalAIServiceError(
            'clinical_ai_invalid_response', 'Clinical AI returned an invalid assessment.', 502, request_id,
        ) from None
    try:
        analysis = AnalyzerResponse.model_validate(response_body)
    except ValidationError as exc:
        issues = [
            {
                'location': '.'.join(str(part) for part in error['loc']),
                'type': error['type'],
            }
            for error in exc.errors(include_input=False, include_context=False)
        ]
        logger.warning('Clinical AI response schema mismatch request_id=%s issues=%s', request_id, issues[:20])
        raise ClinicalAIServiceError(
            'clinical_ai_invalid_response', 'Clinical AI returned an invalid assessment.', 502, request_id,
        ) from None
    if analysis.triage.requires_human_review is not True:
        logger.warning('Clinical AI response rejected request_id=%s reason=human_review_required', request_id)
        raise ClinicalAIServiceError(
            'clinical_ai_invalid_response', 'Clinical AI returned an invalid assessment.', 502, request_id,
        )
    result = analysis.model_dump()
    result['request_id'] = request_id
    return result
