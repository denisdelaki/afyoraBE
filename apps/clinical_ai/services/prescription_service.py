import logging
from typing import Dict, Any, Tuple
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from pharmacy.models import Prescription, Drug
from clinical_ai.models import ClinicalAIConsultation, ClinicalAIRecommendation
from clinical_ai.services.audit_service import log_ai_audit_event

logger = logging.getLogger('clinical_ai')


def approve_ai_prescription(
    user,
    data: Dict[str, Any],
    ip_address: str = None,
    user_agent: str = "",
) -> Tuple[Prescription, Dict[str, Any]]:
    """
    Clinician approval workflow for AI-recommended medication.
    The authenticated clinician IS the author of the final signed prescription.
    
    Verifies clinician authentication and facility boundary.
    Creates a formal prescription in the pharmacy system (`pharmacy.models.Prescription`).
    Stores differences between AI recommendation and clinician's final prescription.
    """
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("User is not authenticated or active.")

    facility = getattr(user, 'facility', None)
    if not facility:
        raise PermissionDenied("User must belong to a facility.")

    # Only clinicians (doctors, nurses with prescribing rights, facility admins) can finalize prescriptions
    role = getattr(user, 'role', 'staff')
    if role not in ('doctor', 'facility_admin', 'admin'):
        raise PermissionDenied("Only authenticated clinicians are authorized to sign prescriptions.")

    consultation_id = data.get('consultation_id')
    recommendation_id = data.get('recommendation_id')
    patient_id_str = data.get('patient_id')
    drugs_list = data.get('drugs', [])

    if not patient_id_str:
        raise ValidationError({"patient_id": "Patient ID is required."})
    if not isinstance(drugs_list, list) or not drugs_list:
        raise ValidationError({"drugs": "A list of prescribed medications is required."})

    # Optional linkage to AI recommendation
    ai_recommendation_data = None
    if recommendation_id:
        try:
            rec = ClinicalAIRecommendation.objects.get(id=int(recommendation_id), consultation__facility=facility)
            ai_recommendation_data = rec.recommendation
            rec.clinician_action = 'accepted' if not data.get('is_modified') else 'modified'
            rec.clinician_modified_value = drugs_list
            rec.reviewed_by = user
            rec.reviewed_at = timezone.now()
            rec.save()
        except (ClinicalAIRecommendation.DoesNotExist, ValueError):
            logger.warning("AI Recommendation %s not found for prescription approval", recommendation_id)

    # Generate prescription ID
    today_str = timezone.now().strftime("%Y%m%d")
    count = Prescription.objects.filter(facility=facility).count() + 1
    prescription_id = f"RX-{today_str}-{count:04d}"

    # Build signed prescription in existing pharmacy app model
    doctor_identifier = user.username or f"DOC-{user.id}"

    prescription = Prescription.objects.create(
        facility=facility,
        prescription_id=prescription_id,
        patient_id=str(patient_id_str),
        doctor_id=doctor_identifier,
        drugs=drugs_list,
        status='Pending',
        date=timezone.now().date(),
    )

    # Compute differences between AI recommendation and final clinician prescription
    differences = {
        'ai_recommendation': ai_recommendation_data,
        'final_clinician_prescription': drugs_list,
        'is_modified': data.get('is_modified', False),
        'modification_notes': data.get('modification_notes', ''),
    }

    # Log audit event
    log_ai_audit_event(
        facility=facility,
        user=user,
        patient_ref=str(patient_id_str),
        consultation_ref=str(consultation_id or ''),
        event_type='prescription_finalized',
        action_details={
            'prescription_id': prescription.prescription_id,
            'doctor_id': doctor_identifier,
            'drug_count': len(drugs_list),
            'differences': differences,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return prescription, differences
