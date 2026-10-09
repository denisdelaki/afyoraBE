import logging
from typing import Dict, Any
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from clinical_ai.models import (
    ClinicalAIConsultation,
    ClinicalAIRecommendation,
    ClinicalAIFeedback,
)
from clinical_ai.services.audit_service import log_ai_audit_event

logger = logging.getLogger('clinical_ai')


def record_clinician_feedback(
    user,
    data: Dict[str, Any],
    ip_address: str = None,
    user_agent: str = "",
) -> ClinicalAIFeedback:
    """
    Records clinician feedback on AI recommendations.
    Applies data anonymization to strip PHI before saving anonymized payload.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    facility = getattr(user, 'facility', None)
    if not facility:
        raise PermissionDenied("User facility context required.")

    consultation_id = data.get('consultation_id') or data.get('consultation')
    if not consultation_id:
        raise ValidationError({"consultation_id": "Consultation ID is required."})

    try:
        consultation = ClinicalAIConsultation.objects.get(
            id=int(consultation_id),
            facility=facility,
        )
    except (ClinicalAIConsultation.DoesNotExist, ValueError):
        raise NotFound(f"AI Consultation '{consultation_id}' not found in your facility.")

    recommendation = None
    rec_id = data.get('recommendation_id') or data.get('recommendation')
    if rec_id:
        try:
            recommendation = ClinicalAIRecommendation.objects.get(
                id=int(rec_id),
                consultation=consultation,
            )
        except (ClinicalAIRecommendation.DoesNotExist, ValueError):
            logger.warning("Recommendation %s not found for consultation %s", rec_id, consultation.id)

    action = (data.get('action') or data.get('clinician_action') or 'accepted').lower()
    if action not in ('accepted', 'rejected', 'modified'):
        raise ValidationError({"action": "Action must be 'accepted', 'rejected', or 'modified'."})

    feedback_text = data.get('feedback', '') or data.get('feedback_text', '')
    rating = data.get('rating')
    modified_value = data.get('modified_value')

    # Update recommendation clinician_action if recommendation object exists
    if recommendation:
        recommendation.clinician_action = action
        if modified_value:
            recommendation.clinician_modified_value = modified_value
        recommendation.reviewed_by = user
        recommendation.save()

    # Build anonymized payload (strips patient name, MRN, clinician identity, exact timestamps)
    anonymized_payload = {
        'model_version': consultation.model_version,
        'knowledge_version': consultation.knowledge_version,
        'action': action,
        'rating': rating,
        'chief_complaint': consultation.chief_complaint,
        'symptoms': consultation.symptoms,
        'vitals_snapshot': consultation.vitals_snapshot,
        'recommendation_type': recommendation.recommendation_type if recommendation else 'general',
        'ai_recommendation_summary': recommendation.recommendation if recommendation else None,
        'feedback_text': feedback_text,
        'modified_value': modified_value,
    }

    feedback = ClinicalAIFeedback.objects.create(
        consultation=consultation,
        recommendation=recommendation,
        clinician=user,
        facility=facility,
        rating=rating if isinstance(rating, int) and 1 <= rating <= 5 else None,
        action=action,
        feedback_text=feedback_text,
        modified_value=modified_value,
        model_version=consultation.model_version,
        is_anonymized=True,
        anonymized_payload=anonymized_payload,
    )

    # Log audit event
    log_ai_audit_event(
        facility=facility,
        user=user,
        patient_ref=str(consultation.patient.patient_id),
        consultation_ref=str(consultation.id),
        event_type=f'recommendation_{action}' if action in ('accepted', 'rejected', 'modified') else 'feedback_submitted',
        action_details={
            'feedback_id': feedback.id,
            'action': action,
            'rating': rating,
            'model_version': consultation.model_version,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return feedback
