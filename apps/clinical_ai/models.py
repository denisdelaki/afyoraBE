from django.db import models
from core.models import BaseModel, Facility, User
from patients.models import Patient, EhrRecord


class ClinicalAIModelVersion(BaseModel):
    """Tracks versions of AI models, prompt engineering, rulesets, and knowledge bases."""
    name = models.CharField(max_length=100, default='Afyora Clinical CDS')
    version = models.CharField(max_length=50, default='v1.0.0')
    prompt_version = models.CharField(max_length=50, default='p1.0.0')
    clinical_rules_version = models.CharField(max_length=50, default='r1.0.0')
    medication_db_version = models.CharField(max_length=50, default='m1.0.0')
    guideline_version = models.CharField(max_length=50, default='g1.0.0')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} {self.version} (Rules: {self.clinical_rules_version})"


class ClinicalAIConsultation(BaseModel):
    """
    Tracks a specific AI Clinical Decision Support session.
    Represents an advisory evaluation requested by an authenticated clinician.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='ai_consultations',
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='ai_consultations',
    )
    consultation_record = models.ForeignKey(
        EhrRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_consultations',
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='requested_ai_consultations',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    request_hash = models.CharField(max_length=64, blank=True)
    chief_complaint = models.TextField(blank=True)
    symptoms = models.TextField(blank=True)
    vitals_snapshot = models.JSONField(default=dict, blank=True)
    labs_snapshot = models.JSONField(default=list, blank=True)
    imaging_snapshot = models.JSONField(default=list, blank=True)
    clinical_summary = models.TextField(blank=True)
    model_version = models.CharField(max_length=100, default='v1.0.0')
    knowledge_version = models.CharField(max_length=100, default='v1.0.0')
    raw_response = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['facility', 'patient']),
            models.Index(fields=['facility', 'requested_by']),
            models.Index(fields=['facility', 'status']),
        ]

    def __str__(self):
        return f"AI Consult {self.id} - Patient {self.patient.patient_id} ({self.status})"


class ClinicalAIRecommendation(BaseModel):
    """
    Individual structured recommendations produced by the Clinical AI.
    Requires explicit clinician review before any action.
    """
    TYPE_CHOICES = (
        ('differential_diagnosis', 'Differential Diagnosis'),
        ('treatment_recommendation', 'Treatment Recommendation'),
        ('investigation', 'Recommended Investigation'),
        ('safety_alert', 'Medication Safety Alert'),
        ('red_flag', 'Red Flag Emergency Alert'),
        ('lifestyle', 'Diet & Lifestyle Guidance'),
        ('patient_education', 'Patient Education'),
        ('follow_up', 'Follow-up Recommendation'),
    )

    CONFIDENCE_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('unknown', 'Unknown'),
    )

    ACTION_CHOICES = (
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('modified', 'Modified'),
    )

    consultation = models.ForeignKey(
        ClinicalAIConsultation,
        on_delete=models.CASCADE,
        related_name='recommendations',
    )
    recommendation_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    recommendation = models.JSONField(default=dict)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default='medium')
    evidence = models.JSONField(default=list, blank=True)
    clinician_action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='pending')
    clinician_modified_value = models.JSONField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_ai_recommendations',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['consultation', 'recommendation_type']),
            models.Index(fields=['consultation', 'clinician_action']),
        ]

    def __str__(self):
        return f"Rec {self.id} [{self.recommendation_type}] - Status: {self.clinician_action}"


class ClinicalAIFeedback(BaseModel):
    """
    Captures clinician feedback on AI recommendations for evaluation & governance.
    Data is stored in isolated, auditable tables and can be anonymized before analysis.
    """
    ACTION_CHOICES = (
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('modified', 'Modified'),
    )

    consultation = models.ForeignKey(
        ClinicalAIConsultation,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    recommendation = models.ForeignKey(
        ClinicalAIRecommendation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks',
    )
    clinician = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='clinical_ai_feedbacks',
    )
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='clinical_ai_feedbacks',
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    feedback_text = models.TextField(blank=True)
    modified_value = models.JSONField(null=True, blank=True)
    model_version = models.CharField(max_length=100, blank=True)
    is_anonymized = models.BooleanField(default=False)
    anonymized_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['facility', 'action']),
            models.Index(fields=['clinician', 'created_at']),
        ]

    def __str__(self):
        return f"Feedback {self.id} by {self.clinician.username} [{self.action}]"


class ClinicalAIAuditEvent(models.Model):
    """
    Immutable audit record for every AI consultation request and clinician action.
    Meets healthcare compliance standards (minimal PHI logging).
    """
    EVENT_CHOICES = (
        ('consultation_requested', 'Consultation Requested'),
        ('context_accessed', 'Patient Context Accessed'),
        ('response_generated', 'AI Response Generated'),
        ('recommendation_accepted', 'Recommendation Accepted'),
        ('recommendation_rejected', 'Recommendation Rejected'),
        ('recommendation_modified', 'Recommendation Modified'),
        ('prescription_finalized', 'Prescription Finalized'),
        ('feedback_submitted', 'Feedback Submitted'),
        ('security_violation', 'Security Violation'),
        ('service_fallback', 'Service Fallback Triggered'),
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='ai_audit_events',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='ai_audit_events',
    )
    patient_ref = models.CharField(max_length=100, help_text='Pseudonymized or ID reference')
    consultation_ref = models.CharField(max_length=100, blank=True)
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    action_details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['facility', 'created_at']),
            models.Index(fields=['facility', 'event_type']),
            models.Index(fields=['user', 'event_type']),
        ]

    def __str__(self):
        return f"Audit {self.id} [{self.event_type}] by User {self.user_id} @ {self.created_at}"
