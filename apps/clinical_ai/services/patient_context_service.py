import logging
from typing import Dict, Any, List
from django.utils import timezone
from datetime import timedelta

from patients.models import Patient, EhrRecord, ProblemItem, AllergyItem
from pharmacy.models import Prescription
from laboratory.models import LabRequest, LabResult
from radiology.models import ImagingRequest, ImagingReport

logger = logging.getLogger('clinical_ai')


def get_patient_clinical_context(patient: Patient, facility_id: int, max_months: int = 12) -> Dict[str, Any]:
    """
    Retrieves clinically relevant patient history applying strict data minimization.
    Only pulls active chronic conditions, active allergies, recent prescriptions (last 12 months),
    recent lab results, and recent imaging reports.
    """
    cutoff_date = timezone.now().date() - timedelta(days=max_months * 30)

    # Demographics
    demographics = {
        'patient_id': patient.patient_id,
        'age': patient.age,
        'gender': patient.gender,
        'date_of_birth': str(patient.date_of_birth) if patient.date_of_birth else None,
        'blood_group': patient.blood_group,
    }

    # Allergies (Structured + legacy field)
    allergies: List[Dict[str, Any]] = []
    structured_allergies = AllergyItem.objects.filter(
        facility_id=facility_id,
        patient=patient,
        is_active=True,
    )
    for alg in structured_allergies:
        allergies.append({
            'allergen_name': alg.allergen_name,
            'allergen_code': alg.allergen_code,
            'allergy_type': alg.allergy_type,
            'severity': alg.severity,
            'reaction': alg.reaction,
        })
    if not allergies and patient.allergies:
        # Fallback to string text if structured items not present
        allergies.append({
            'allergen_name': patient.allergies,
            'allergen_code': '',
            'allergy_type': 'Unspecified',
            'severity': 'Unknown',
            'reaction': '',
        })

    # Chronic Conditions / Problem List
    problems: List[Dict[str, Any]] = []
    problem_qs = ProblemItem.objects.filter(
        facility_id=facility_id,
        patient=patient,
        status='Active',
        is_active=True,
    )
    for p in problem_qs:
        problems.append({
            'display': p.display,
            'code': p.code,
            'system': p.system,
            'status': p.status,
            'onset_date': str(p.onset_date) if p.onset_date else None,
        })

    # EHR Records (Previous Diagnoses & Summaries, limited to top 5 recent)
    ehr_qs = EhrRecord.objects.filter(
        facility_id=facility_id,
        patient=patient,
        is_active=True,
    ).order_by('-date', '-created_at')[:5]

    previous_diagnoses: List[Dict[str, Any]] = []
    for record in ehr_qs:
        previous_diagnoses.append({
            'date': str(record.date),
            'diagnosis': record.diagnosis,
            'diagnosis_code': record.diagnosis_code,
            'symptoms': record.symptoms,
            'treatment': record.treatment,
            'doctor': record.doctor,
        })

    # Prescriptions / Current Medications
    rx_qs = Prescription.objects.filter(
        facility_id=facility_id,
        patient_id=patient.patient_id,
        is_active=True,
        date__gte=cutoff_date,
    ).order_by('-date')[:10]

    current_medications: List[Dict[str, Any]] = []
    for rx in rx_qs:
        current_medications.append({
            'prescription_id': rx.prescription_id,
            'date': str(rx.date),
            'status': rx.status,
            'drugs': rx.drugs if isinstance(rx.drugs, list) else [],
        })

    # Recent Lab Results
    lab_req_ids = LabRequest.objects.filter(
        facility_id=facility_id,
        patient_id=patient.patient_id,
        order_date__gte=cutoff_date,
    ).values_list('id', flat=True)

    lab_results: List[Dict[str, Any]] = []
    lab_res_qs = LabResult.objects.filter(
        facility_id=facility_id,
        request_id__in=lab_req_ids,
        is_active=True,
    ).select_related('request', 'request__test').order_by('-completed_date')[:10]

    for res in lab_res_qs:
        lab_results.append({
            'lab_id': res.lab_id,
            'test_name': res.request.test.name if res.request and res.request.test else "Lab Test",
            'completed_date': str(res.completed_date),
            'status': res.status,
            'parameters': res.parameters if isinstance(res.parameters, list) else [],
            'remarks': res.remarks,
        })

    # Recent Radiology / Imaging Reports
    img_req_ids = ImagingRequest.objects.filter(
        facility_id=facility_id,
        patient_id=patient.patient_id,
        order_date__gte=cutoff_date,
    ).values_list('id', flat=True)

    imaging_reports: List[Dict[str, Any]] = []
    img_rep_qs = ImagingReport.objects.filter(
        facility_id=facility_id,
        request_id__in=img_req_ids,
        is_active=True,
    ).select_related('request', 'request__study').order_by('-scan_date')[:5]

    for rep in img_rep_qs:
        imaging_reports.append({
            'report_id': rep.report_id,
            'study_name': rep.request.study.name if rep.request and rep.request.study else "Imaging Study",
            'modality': rep.request.study.modality if rep.request and rep.request.study else "",
            'body_part': rep.request.study.body_part if rep.request and rep.request.study else "",
            'scan_date': str(rep.scan_date),
            'findings': rep.findings,
            'impression': rep.impression,
            'status': rep.status,
        })

    return {
        'demographics': demographics,
        'allergies': allergies,
        'active_problems': problems,
        'previous_diagnoses': previous_diagnoses,
        'current_medications': current_medications,
        'recent_lab_results': lab_results,
        'recent_imaging_reports': imaging_reports,
    }
