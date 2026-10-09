from django.contrib import admin
from clinical_ai.models import (
    ClinicalAIModelVersion,
    ClinicalAIConsultation,
    ClinicalAIRecommendation,
    ClinicalAIFeedback,
    ClinicalAIAuditEvent,
)


@admin.register(ClinicalAIModelVersion)
class ClinicalAIModelVersionAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'prompt_version', 'clinical_rules_version', 'is_active', 'created_at')
    list_filter = ('is_active',)


@admin.register(ClinicalAIConsultation)
class ClinicalAIConsultationAdmin(admin.ModelAdmin):
    list_display = ('id', 'facility', 'patient', 'requested_by', 'status', 'model_version', 'created_at')
    list_filter = ('status', 'facility', 'created_at')
    search_fields = ('patient__patient_id', 'requested_by__username', 'chief_complaint')


@admin.register(ClinicalAIRecommendation)
class ClinicalAIRecommendationAdmin(admin.ModelAdmin):
    list_display = ('id', 'consultation', 'recommendation_type', 'confidence', 'clinician_action', 'reviewed_by', 'created_at')
    list_filter = ('recommendation_type', 'confidence', 'clinician_action')


@admin.register(ClinicalAIFeedback)
class ClinicalAIFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'consultation', 'clinician', 'action', 'rating', 'model_version', 'created_at')
    list_filter = ('action', 'rating', 'created_at')


@admin.register(ClinicalAIAuditEvent)
class ClinicalAIAuditEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'facility', 'user', 'patient_ref', 'event_type', 'ip_address', 'created_at')
    list_filter = ('event_type', 'facility', 'created_at')
    readonly_fields = ('facility', 'user', 'patient_ref', 'consultation_ref', 'event_type', 'action_details', 'ip_address', 'user_agent', 'created_at')

    def has_delete_permission(self, request, obj=None):
        return False
