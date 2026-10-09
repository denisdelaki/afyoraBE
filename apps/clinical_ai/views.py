import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.exceptions import PermissionDenied, NotFound

from patients.models import Patient
from clinical_ai.models import ClinicalAIConsultation
from clinical_ai.permissions import IsClinicianAuthorizedForClinicalAI
from clinical_ai.serializers import (
    ClinicalAIConsultationRequestSerializer,
    ClinicalAIConsultationDetailSerializer,
    ClinicalAIFeedbackSerializer,
    ClinicalAIPrescriptionApprovalSerializer,
)
from clinical_ai.services.consultation_service import run_clinical_ai_consultation
from clinical_ai.services.patient_context_service import get_patient_clinical_context
from clinical_ai.services.ai_gateway import ClinicalAIServiceError
from clinical_ai.services.feedback_service import record_clinician_feedback
from clinical_ai.services.prescription_service import approve_ai_prescription

logger = logging.getLogger('clinical_ai')


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class ClinicalAIConsultationView(APIView):
    """
    POST /api/clinical-ai/consultation/
    Request Clinical Decision Support AI analysis for a patient consultation.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def post(self, request, *args, **kwargs):
        serializer = ClinicalAIConsultationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        try:
            ai_consultation, ai_response = run_clinical_ai_consultation(
                user=request.user,
                data=serializer.validated_data,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except ClinicalAIServiceError as exc:
            return Response(exc.detail, status=exc.status_code, headers={'X-Request-ID': exc.request_id})
        return Response(ai_response, status=status.HTTP_200_OK, headers={'X-Request-ID': ai_response['request_id']})


class ClinicalAIPatientHistoryView(APIView):
    """
    GET /api/clinical-ai/patient-history/{patient_id}/
    Returns data-minimized, clinically relevant patient history.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def get(self, request, patient_id, *args, **kwargs):
        facility = request.user.facility
        try:
            if str(patient_id).isdigit():
                patient = Patient.objects.get(id=int(patient_id), facility=facility, is_active=True)
            else:
                patient = Patient.objects.get(patient_id=str(patient_id), facility=facility, is_active=True)
        except Patient.DoesNotExist:
            raise NotFound(f"Patient '{patient_id}' not found in your facility.")

        context = get_patient_clinical_context(patient, facility.id)
        return Response(context, status=status.HTTP_200_OK)


class ClinicalAIChatView(APIView):
    """
    POST /api/clinical-ai/chat/
    Retired: the standalone integration does not expose a chat endpoint.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def post(self, request, *args, **kwargs):
        return Response({
            'error': {'code': 'chat_not_supported', 'message': 'Standalone Clinical AI supports consultation analysis only.'},
        }, status=status.HTTP_410_GONE)


class ClinicalAIFeedbackView(APIView):
    """
    POST /api/clinical-ai/feedback/
    Records clinician feedback (accepted/rejected/modified) on AI recommendations.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def post(self, request, *args, **kwargs):
        serializer = ClinicalAIFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        feedback = record_clinician_feedback(
            user=request.user,
            data=serializer.validated_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return Response({
            'status': 'success',
            'feedback_id': feedback.id,
            'message': 'Clinician feedback recorded successfully.',
        }, status=status.HTTP_201_CREATED)


class ClinicalAIPrescriptionApproveView(APIView):
    """
    POST /api/clinical-ai/prescription/approve/
    Finalizes an AI recommendation into a signed clinician prescription in pharmacy.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def post(self, request, *args, **kwargs):
        serializer = ClinicalAIPrescriptionApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        prescription, differences = approve_ai_prescription(
            user=request.user,
            data=serializer.validated_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return Response({
            'status': 'success',
            'prescription_id': prescription.prescription_id,
            'status_code': prescription.status,
            'differences': differences,
            'signed_by': prescription.doctor_id,
            'message': 'Prescription finalized and signed by clinician.',
        }, status=status.HTTP_201_CREATED)


class ClinicalAIConsultationDetailView(APIView):
    """
    GET /api/clinical-ai/consultation/{consultation_id}/
    Retrieve structured details of a previous AI consultation.
    """
    permission_classes = [permissions.IsAuthenticated, IsClinicianAuthorizedForClinicalAI]

    def get(self, request, consultation_id, *args, **kwargs):
        facility = request.user.facility
        try:
            consultation = ClinicalAIConsultation.objects.get(
                id=int(consultation_id),
                facility=facility,
            )
        except (ClinicalAIConsultation.DoesNotExist, ValueError):
            raise NotFound(f"AI Consultation '{consultation_id}' not found.")

        serializer = ClinicalAIConsultationDetailSerializer(consultation)
        return Response(serializer.data, status=status.HTTP_200_OK)
