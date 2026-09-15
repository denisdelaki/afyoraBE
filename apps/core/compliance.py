"""
apps/core/compliance.py

Kenya Digital Health Agency (DHA) compliance utilities for AfyoraHMS.

Provides:
  - log_concept_provenance(): write a ConceptProvenanceLog entry after every
    clinical record save that carries a coded diagnosis.
  - DhaComplianceHeaderMiddleware: adds X-DHA-Facility-MFL and
    X-KNHTS-Compliant headers to every authenticated API response.

These are required for DHA certification under KHIS / Kenya Health
Information Systems Policy 2024.
"""

import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provenance log helper
# ---------------------------------------------------------------------------

def log_concept_provenance(*, user, facility, record_type, record_id, concept):
    """
    Write a ConceptProvenanceLog entry for a coded clinical concept.

    This function is intentionally non-fatal: if the log write fails for any
    reason, the failure is logged as a warning but the clinical record save
    is NOT rolled back.  A failed provenance log is a compliance concern to
    be investigated, but it must never cause data loss for the clinician.

    Parameters
    ----------
    user        : core.models.User or None
    facility    : core.models.Facility
    record_type : str  -- one of 'ehr', 'visit', 'lab', 'radiology'
    record_id   : str  -- str(pk) of the saved clinical record
    concept     : dict -- must contain 'code_system'/'diagnosis_system',
                         'code'/'diagnosis_code', and optionally 'display'/'diagnosis_text'
    """
    from .models import ConceptProvenanceLog  # local import to avoid circular refs

    code_system = (concept.get('code_system') or concept.get('diagnosis_system') or '').strip()
    code = (concept.get('code') or concept.get('diagnosis_code') or '').strip()
    display = (concept.get('display') or concept.get('diagnosis_text') or '').strip()

    if not code_system or not code:
        # Nothing to log -- no coded concept present
        return

    try:
        ConceptProvenanceLog.objects.create(
            facility=facility,
            user=user,
            code_system=code_system,
            code=code,
            display=display,
            record_type=record_type,
            record_id=str(record_id),
            looked_up_at=timezone.now(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'ConceptProvenanceLog write failed for %s/%s [%s:%s]: %s',
            record_type,
            record_id,
            code_system,
            code,
            exc,
        )


# ---------------------------------------------------------------------------
# DHA compliance response middleware
# ---------------------------------------------------------------------------

class DhaComplianceHeaderMiddleware:
    """
    Injects DHA-required HTTP headers into every API response.

    Headers added:
      X-DHA-Facility-MFL  -- Ministry of Health MFL code (from MFL_CODE setting
                             or facility registration_number for authenticated users)
      X-KNHTS-Compliant   -- 'true' when KNHTS_API_KEY is configured, 'false' otherwise
      X-DHA-System        -- Always 'AfyoraHMS' for identification in MoH integrations
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only annotate API responses (skip admin, static, media)
        if not request.path.startswith('/api/'):
            return response

        # Facility MFL: prefer env-level MFL_CODE, fall back to authenticated
        # user's facility registration_number (used as MFL proxy pre-registration)
        mfl_code = getattr(settings, 'MFL_CODE', '').strip()
        if not mfl_code:
            user = getattr(request, 'user', None)
            if user and getattr(user, 'is_authenticated', False):
                facility = getattr(user, 'facility', None)
                if facility:
                    mfl_code = getattr(facility, 'registration_number', '') or ''

        if mfl_code:
            response['X-DHA-Facility-MFL'] = mfl_code

        # KNHTS integration status
        knhts_configured = bool(getattr(settings, 'KNHTS_API_KEY', '').strip())
        response['X-KNHTS-Compliant'] = 'true' if knhts_configured else 'false'

        # System identification for MoH / DHA integrations
        response['X-DHA-System'] = 'AfyoraHMS'

        return response
