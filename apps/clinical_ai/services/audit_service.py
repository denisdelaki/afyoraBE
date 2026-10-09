import logging
from clinical_ai.models import ClinicalAIAuditEvent

logger = logging.getLogger('clinical_ai')


def log_ai_audit_event(
    *,
    facility,
    user,
    patient_ref: str,
    event_type: str,
    consultation_ref: str = "",
    action_details: dict = None,
    ip_address: str = None,
    user_agent: str = "",
) -> ClinicalAIAuditEvent:
    """
    Creates an immutable audit log entry for Clinical AI actions.
    Ensures minimum necessary metadata is saved and PHI is not logged into plaintext.
    """
    try:
        details = action_details or {}
        event = ClinicalAIAuditEvent.objects.create(
            facility=facility,
            user=user,
            patient_ref=str(patient_ref),
            consultation_ref=str(consultation_ref),
            event_type=event_type,
            action_details=details,
            ip_address=ip_address,
            user_agent=user_agent[:255] if user_agent else "",
        )
        logger.info(
            "Clinical AI Audit Event [%s] logged for Facility %s, User %s, PatientRef %s",
            event_type,
            facility.id if facility else "None",
            user.id if user else "None",
            patient_ref,
        )
        return event
    except Exception as exc:
        logger.error("Failed to log Clinical AI audit event: %s", exc, exc_info=True)
        return None
