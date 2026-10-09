import hashlib
import json
import logging
import math
from typing import Dict, Any, Tuple
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from patients.models import Patient, EhrRecord
from clinical_ai.models import (
    ClinicalAIConsultation,
    ClinicalAIRecommendation,
)
from clinical_ai.services.patient_context_service import get_patient_clinical_context
from clinical_ai.services.ai_gateway import call_clinical_ai_analysis, ClinicalAIServiceError
from clinical_ai.services.audit_service import log_ai_audit_event

logger = logging.getLogger('clinical_ai')


def build_analysis_payload(patient, data, context):
    symptoms = data.get('symptoms', '')
    symptoms = symptoms if isinstance(symptoms, list) else ([symptoms] if symptoms else [])
    chief_complaint = data.get('chief_complaint', '').strip()
    if not symptoms and chief_complaint:
        symptoms = [chief_complaint]
    observations = [item for item in data.get('observations', []) if item]
    if chief_complaint and chief_complaint not in symptoms:
        observations.append(chief_complaint)
    for field in ('breastfeeding', 'weight_kg', 'renal_function', 'hepatic_function'):
        if data.get(field) is not None:
            observations.append(f'{field}: {data[field]}')
    pregnancy_status = str(data.get('pregnancy_status') or '').strip().lower()
    is_pregnant = data.get('is_pregnant')
    if is_pregnant is None and pregnancy_status in ('yes', 'true', 'pregnant'):
        is_pregnant = True
    elif is_pregnant is None and pregnancy_status in ('no', 'false', 'not pregnant'):
        is_pregnant = False
    age = patient.age
    if age is not None and not 0 <= age <= 130:
        raise ValidationError({'age': 'Patient age must be between 0 and 130.'})
    medications = []
    for prescription in context.get('current_medications', []):
        for drug in prescription.get('drugs', []):
            if isinstance(drug, str):
                medications.append(drug)
            elif isinstance(drug, dict):
                description = ' '.join(str(drug[key]) for key in ('name', 'dosage', 'frequency', 'duration') if drug.get(key))
                if description:
                    medications.append(description)
    def map_labs(results):
        normalized_results = []
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                raise ValidationError({
                    'laboratory_results': f'Lab result {index + 1} must include a test name and numeric value.'
                })
            test_name = result.get('test') or result.get('test_name') or result.get('testName') or result.get('name') or 'Lab Test'
            parameters = result.get('parameters')
            if isinstance(parameters, list) and parameters:
                for parameter in parameters:
                    if isinstance(parameter, dict):
                        normalized_results.append({
                            'test': parameter.get('test') or parameter.get('name') or test_name,
                            'value': normalized_lab_value(parameter.get('value', result.get('value')), index),
                            'unit': parameter.get('unit', result.get('unit', '')),
                        })
                continue
            normalized_results.append({
                'test': test_name,
                'value': normalized_lab_value(result.get('value'), index),
                'unit': result.get('unit', ''),
            })
        return normalized_results

    def normalized_lab_value(value, index):
        if isinstance(value, bool) or value is None:
            raise ValidationError({
                'laboratory_results': f'Lab result {index + 1} must include a value.'
            })
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValidationError({
                    'laboratory_results': f'Lab result {index + 1} must include a value.'
                })
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            if isinstance(value, str):
                return value
            raise ValidationError({'laboratory_results': f'Lab result {index + 1} has an invalid value.'}) from None
        if not math.isfinite(numeric_value):
            raise ValidationError({
                'laboratory_results': f'Lab result {index + 1} must have a finite numeric value.'
            })
        return numeric_value

    def first_value(mapping, *keys):
        return next((mapping[key] for key in keys if mapping.get(key) is not None), None)

    def normalized_number(value, field_name):
        if value is None or value == '':
            return None
        if isinstance(value, bool):
            raise ValidationError({'vitals': f'{field_name} must be numeric.'})
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValidationError({'vitals': f'{field_name} must be numeric.'}) from None
        if not math.isfinite(number):
            raise ValidationError({'vitals': f'{field_name} must be a finite number.'})
        return int(number) if number.is_integer() else number

    def map_radiology(results):
        mapped = []
        for result in results:
            if isinstance(result, str):
                mapped.append(result)
            elif isinstance(result, dict):
                details = [
                    str(value).strip()
                    for value in (
                        first_value(result, 'modality'),
                        first_value(result, 'study_name', 'studyName', 'name'),
                        first_value(result, 'body_part', 'bodyPart'),
                        first_value(result, 'findings'),
                        first_value(result, 'impression'),
                        first_value(result, 'report'),
                    )
                    if value
                ]
                if details:
                    mapped.append(': '.join(details[:3]) + ('. ' + '; '.join(details[3:]) if len(details) > 3 else ''))
        return mapped

    incoming_vitals = data.get('vitals', {})
    vital_aliases = {
        'temperature': ('temperature', 'temperatureC', 'temperature_c'),
        'heart_rate': ('heart_rate', 'heartRateBpm', 'heartRate', 'heart_rate_bpm'),
        'respiratory_rate': ('respiratory_rate', 'respiratoryRate', 'respiratory_rate_bpm', 'respiratoryRateBpm'),
        'oxygen_saturation': ('oxygen_saturation', 'oxygenSaturation', 'spo2Percent', 'spo2_percent', 'spo2'),
    }
    vitals = {}
    for output_name, aliases in vital_aliases.items():
        value = normalized_number(first_value(incoming_vitals, *aliases), output_name)
        if value is not None:
            vitals[output_name] = value
    blood_pressure = first_value(incoming_vitals, 'blood_pressure', 'bloodPressure')
    systolic = normalized_number(first_value(incoming_vitals, 'systolic_bp', 'systolicBp'), 'systolic blood pressure')
    diastolic = normalized_number(first_value(incoming_vitals, 'diastolic_bp', 'diastolicBp'), 'diastolic blood pressure')
    if blood_pressure:
        vitals['blood_pressure'] = str(blood_pressure).strip()
    elif systolic is not None and diastolic is not None:
        vitals['blood_pressure'] = f'{systolic}/{diastolic}'

    height = normalized_number(first_value(incoming_vitals, 'height_cm', 'heightCm'), 'height')
    if height is not None:
        observations.append(f'height_cm: {height}')
    weight = normalized_number(
        data.get('weight_kg') if data.get('weight_kg') is not None else first_value(incoming_vitals, 'weight_kg', 'weightKg'),
        'weight',
    )
    if weight is not None and data.get('weight_kg') is None:
        observations.append(f'weight_kg: {weight}')
    glucose = normalized_number(
        first_value(incoming_vitals, 'blood_glucose', 'blood_glucose_mmol', 'bloodGlucoseMmol', 'bloodGlucose'),
        'blood glucose',
    )
    if glucose is not None:
        observations.append(f'blood_glucose_mmol: {glucose}')

    lab_results = first_value(data, 'laboratory_results', 'laboratoryResults', 'labs') or context.get('recent_lab_results', [])
    imaging_results = first_value(data, 'imaging_reports', 'imagingReports', 'radiology') or context.get('recent_imaging_reports', [])

    return {
        'age': age,
        'sex': patient.gender or None,
        'is_pregnant': is_pregnant,
        'symptoms': symptoms,
        'medical_history': [problem['display'] for problem in context.get('active_problems', []) if problem.get('display')],
        'allergies': [
            '; '.join(str(allergy[key]) for key in ('allergen_name', 'reaction', 'severity') if allergy.get(key))
            for allergy in context.get('allergies', []) if allergy.get('allergen_name')
        ],
        'current_medications': medications,
        'vitals': vitals,
        'labs': map_labs(lab_results),
        'radiology': map_radiology(imaging_results),
        'previous_diagnoses': [record['diagnosis'] for record in context.get('previous_diagnoses', []) if record.get('diagnosis')],
        'observations': observations,
    }


def package_analysis(analyzer_response, consultation_id):
    triage = analyzer_response['triage']
    urgency = triage['level']
    risk_level = {'routine': 'low', 'urgent': 'high', 'emergency': 'critical'}[urgency]
    referral_reason = triage['recommendation'] or '; '.join(triage['reasons'])
    possible_conditions = [
        {'condition': disease, 'likelihood': 'unspecified', 'supporting_evidence': []}
        for disease in analyzer_response['possible_disease']
    ]
    investigations = analyzer_response['further_labs_to_be_done']
    management_considerations = [triage['recommendation']] if triage['recommendation'] else []
    referral = {
        'required': triage['urgent_care_recommended'],
        'urgency': urgency,
        'reason': referral_reason,
    }
    normalized_analysis = {
        'clinical_summary': analyzer_response['supported_diagnosis'],
        'risk_level': risk_level,
        'possible_conditions': possible_conditions,
        'abnormal_findings': triage['reasons'],
        'recommended_investigations': investigations,
        'management_considerations': management_considerations,
        'medication_considerations': [],
        'red_flags': triage['reasons'] if triage['urgent_care_recommended'] else [],
        'referral_recommendation': referral,
        'confidence': None,
        'requires_human_review': triage['requires_human_review'],
    }
    return {
        **analyzer_response,
        **normalized_analysis,
        'analysis': {
            **{key: value for key, value in analyzer_response.items() if key != 'request_id'},
            **normalized_analysis,
        },
        'consultation_id': str(consultation_id),
        'status': 'success',
        'emergency': urgency == 'emergency',
        'urgency': urgency,
        'differential_diagnoses': [
            {'disease': condition['condition'], 'likelihood': condition['likelihood'],
             'code': '', 'code_system': '', 'confidence': 'unknown',
             'supporting_findings': condition['supporting_evidence'], 'contradicting_findings': [],
             'missing_information': [], 'recommended_confirmation_tests': [],
             'specialist_referral_considerations': referral['reason'] if referral['required'] else None}
            for condition in possible_conditions
        ],
        'recommended_investigations': [
            {'test_name': investigation, 'indication': '', 'urgency': urgency}
            for investigation in investigations
        ],
        'treatment_recommendations': [],
        'medication_safety': [],
        'supportive_measures': management_considerations,
        'dietary_recommendations': [],
        'patient_education': [],
        'follow_up': [],
        'evidence_citations': [],
        'confidence_level': 'unknown',
        'uncertainty': [],
        'missing_information': triage['unassessed_vitals'],
        'specialist_referral': referral['reason'] if referral['required'] else None,
        'model_version': '',
        'knowledge_version': '',
        'mcp_tools_used': [],
        'generated_at': timezone.now().isoformat(),
        'disclaimer': 'Advisory decision support only. A qualified clinician must review this assessment before any diagnosis, referral, or treatment decision.',
    }


def run_clinical_ai_consultation(
    user,
    data: Dict[str, Any],
    ip_address: str = None,
    user_agent: str = "",
) -> Tuple[ClinicalAIConsultation, Dict[str, Any]]:
    """
    Main orchestration service for running a Clinical Decision Support AI consultation in Django.
    
    Validates user & patient facility authorization boundaries server-side.
    Data flow:
      Django REST API -> Server-side Auth Check -> Retrieve Patient Context
    -> Standalone Clinical AI API -> Stored Recommendations
      -> Audit Event -> Strongly Typed Response
    """
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("User is not authenticated or active.")

    facility = getattr(user, 'facility', None)
    if not facility:
        raise PermissionDenied("User is not assigned to an active healthcare facility.")

    # 1. Authorization & Patient Verification
    patient_id_raw = data.get('patient_id') or data.get('patient')
    if not patient_id_raw:
        raise ValidationError({"patient_id": "Patient ID is required."})

    try:
        # Search by primary key ID or facility-unique patient_id string
        if isinstance(patient_id_raw, int) or (isinstance(patient_id_raw, str) and patient_id_raw.isdigit()):
            patient = Patient.objects.get(id=int(patient_id_raw), facility=facility, is_active=True)
        else:
            patient = Patient.objects.get(patient_id=str(patient_id_raw), facility=facility, is_active=True)
    except Patient.DoesNotExist:
        raise NotFound(f"Patient '{patient_id_raw}' was not found in your facility.")

    # Check consultation/EHR record if passed
    consultation_record = None
    consultation_id_raw = data.get('consultation_id') or data.get('consultation')
    if consultation_id_raw:
        try:
            if str(consultation_id_raw).isdigit():
                consultation_record = EhrRecord.objects.get(id=int(consultation_id_raw), facility=facility, patient=patient)
        except EhrRecord.DoesNotExist:
            logger.warning("EHR record %s not found for patient %s", consultation_id_raw, patient.id)

    # 2. Extract clinical payload (never trust clinicianId / facilityId in body)
    chief_complaint = data.get('chief_complaint', '').strip()
    symptom_input = data.get('symptoms', '')
    symptoms = '\n'.join(symptom_input) if isinstance(symptom_input, list) else symptom_input.strip()
    vitals = data.get('vitals', {})
    lab_results = data.get('laboratory_results', []) or data.get('labs', [])
    imaging_reports = data.get('imaging_reports', []) or data.get('imaging', [])

    # 3. Retrieve authorized patient context with data minimization
    patient_context = get_patient_clinical_context(patient, facility.id)

    # Log context access audit event
    log_ai_audit_event(
        facility=facility,
        user=user,
        patient_ref=str(patient.patient_id),
        event_type='context_accessed',
        ip_address=ip_address,
        user_agent=user_agent,
    )

    analysis_payload = build_analysis_payload(patient, data, patient_context)

    # Compute SHA-256 hash of payload
    request_bytes = json.dumps(analysis_payload, sort_keys=True).encode('utf-8')
    request_hash = hashlib.sha256(request_bytes).hexdigest()

    # 5. Create database record for AI consultation
    ai_consultation = ClinicalAIConsultation.objects.create(
        facility=facility,
        patient=patient,
        consultation_record=consultation_record,
        requested_by=user,
        status='pending',
        request_hash=request_hash,
        chief_complaint=chief_complaint,
        symptoms=symptoms,
        vitals_snapshot=vitals if isinstance(vitals, dict) else {},
        labs_snapshot=lab_results if isinstance(lab_results, list) else [],
        imaging_snapshot=imaging_reports if isinstance(imaging_reports, list) else [],
    )

    try:
        analyzer_response = call_clinical_ai_analysis(analysis_payload)
    except ClinicalAIServiceError as exc:
        ai_consultation.status = 'failed'
        ai_consultation.completed_at = timezone.now()
        ai_consultation.save(update_fields=['status', 'completed_at'])
        log_ai_audit_event(
            facility=facility, user=user, patient_ref=str(patient.patient_id),
            consultation_ref=str(ai_consultation.id), event_type='service_fallback',
            action_details={'status': 'failed', 'request_id': exc.request_id, 'http_status': exc.status_code},
            ip_address=ip_address, user_agent=user_agent,
        )
        raise
    ai_response = package_analysis(analyzer_response, ai_consultation.id)

    # 7. Process response and persist recommendations
    with transaction.atomic():
        ai_consultation.status = 'completed'
        ai_consultation.clinical_summary = ai_response['clinical_summary']
        ai_consultation.model_version = ''
        ai_consultation.knowledge_version = ''
        ai_consultation.raw_response = ai_response
        ai_consultation.completed_at = timezone.now()
        ai_consultation.save()
        recommendations = []
        for recommendation_type, values in (
            ('differential_diagnosis', ai_response['differential_diagnoses']),
            ('investigation', ai_response['recommended_investigations']),
            ('safety_alert', ai_response['medication_safety']),
            ('treatment_recommendation', [{'consideration': text} for text in ai_response['management_considerations']]),
        ):
            for value in values:
                recommendations.append(ClinicalAIRecommendation(
                    consultation=ai_consultation, recommendation_type=recommendation_type,
                    recommendation=value, confidence=ai_response['confidence_level'], evidence=[],
                ))
        if ai_response['red_flags']:
            recommendations.append(ClinicalAIRecommendation(
                consultation=ai_consultation, recommendation_type='red_flag',
            recommendation={'red_flags': ai_response['red_flags'], 'urgency': ai_response['urgency']},
                confidence=ai_response['confidence_level'], evidence=[],
            ))
        ClinicalAIRecommendation.objects.bulk_create(recommendations)

    # 8. Log audit event
    log_ai_audit_event(
        facility=facility,
        user=user,
        patient_ref=str(patient.patient_id),
        consultation_ref=str(ai_consultation.id),
        event_type='consultation_requested',
        action_details={
            'ai_consultation_id': ai_consultation.id,
            'status': ai_consultation.status,
            'request_id': ai_response['request_id'],
            'model_version': ai_consultation.model_version,
            'emergency': ai_response.get('emergency', False),
            'has_red_flags': len(ai_response.get('red_flags', [])) > 0,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    ai_response['consultation_id'] = str(ai_consultation.id)
    return ai_consultation, ai_response
