from django.urls import path
from clinical_ai.views import (
    ClinicalAIConsultationView,
    ClinicalAIPatientHistoryView,
    ClinicalAIChatView,
    ClinicalAIFeedbackView,
    ClinicalAIPrescriptionApproveView,
    ClinicalAIConsultationDetailView,
)

urlpatterns = [
    path('consultation/', ClinicalAIConsultationView.as_view(), name='clinical-ai-consultation'),
    path('patient-history/<str:patient_id>/', ClinicalAIPatientHistoryView.as_view(), name='clinical-ai-patient-history'),
    path('chat/', ClinicalAIChatView.as_view(), name='clinical-ai-chat'),
    path('feedback/', ClinicalAIFeedbackView.as_view(), name='clinical-ai-feedback'),
    path('prescription/approve/', ClinicalAIPrescriptionApproveView.as_view(), name='clinical-ai-prescription-approve'),
    path('consultation/<int:consultation_id>/', ClinicalAIConsultationDetailView.as_view(), name='clinical-ai-consultation-detail'),
]
