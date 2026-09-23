from django.db import models


class InsuranceProvider(models.Model):
    """
    Model for Facility Admins to onboard and configure insurance services,
    such as Social Health Authority (SHA / DHA AfyaConnect), NHIF, or Private Payers.
    """

    PAYER_TYPE_CHOICES = (
        ('SOCIAL', 'Social Health Authority (SHA/NHIF)'),
        ('PRIVATE', 'Private Commercial Insurance'),
        ('COMMUNITY', 'Community / Managed Care'),
    )

    ENVIRONMENT_CHOICES = (
        ('UAT', 'Sandbox / UAT Environment'),
        ('PROD', 'Production Middleware'),
    )

    facility_id = models.CharField(max_length=50, default='1')
    name = models.CharField(max_length=255, help_text="e.g. Social Health Authority (SHA)")
    code = models.CharField(max_length=50, unique=True, help_text="Payer code e.g. SHA, NHIF, SLADE_01")
    payer_type = models.CharField(max_length=20, choices=PAYER_TYPE_CHOICES, default='SOCIAL')
    
    # Gateway settings
    gateway_url = models.URLField(
        default='https://ilm-dev.dha.go.ke/uat-middleware',
        help_text="Base URL for DHA AfyaConnect middleware"
    )
    facility_code = models.CharField(max_length=100, default='MOH-FAC-001', help_text="Facility FR/MFL Code")
    api_token = models.TextField(blank=True, null=True, help_text="Bearer Authorization token for DHA API")
    environment = models.CharField(max_length=10, choices=ENVIRONMENT_CHOICES, default='UAT')
    
    is_active = models.BooleanField(default=True)
    sandbox_mode = models.BooleanField(default=True, help_text="Enable mock fallback if DHA middleware is unreachable")
    
    supported_schemes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of schemes supported, e.g. ['Outpatient', 'Inpatient', 'Emergency', 'Capitation']"
    )
    
    last_ping_status = models.CharField(max_length=50, default='Healthy')
    last_ping_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Insurance Provider Config'
        verbose_name_plural = 'Insurance Provider Configs'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} [{self.code}] - {'Active' if self.is_active else 'Inactive'}"


class DHAClaim(models.Model):
    """Local record of virtual claims created via DHA AfyaConnect."""

    SERVICE_TYPE_CHOICES = (
        ('CAPITATION', 'Capitation'),
        ('OUTPATIENT', 'Outpatient'),
        ('INPATIENT', 'Inpatient'),
        ('EMERGENCY', 'Emergency'),
    )

    WORKFLOW_STATE_CHOICES = (
        ('OPEN', 'Open Virtual Claim'),
        ('PENDING_REVIEW', 'Pending Payer Review'),
        ('SUBMITTED', 'Submitted for Reimbursement'),
        ('CLOSED', 'Closed / Cancelled'),
        ('RESUBMITTED', 'Resubmitted'),
    )

    facility_id = models.CharField(max_length=50, default='1')
    claim_id = models.CharField(max_length=100, blank=True, null=True)
    authorization_code = models.CharField(max_length=255, help_text="Consent token returned from visit creation")
    authorization_guid = models.CharField(max_length=255, blank=True, null=True)
    patient_id = models.CharField(max_length=100, help_text="Client Registry ID / National ID")
    patient_name = models.CharField(max_length=255, blank=True, null=True)
    member_number = models.CharField(max_length=100, blank=True, null=True)
    service_type = models.CharField(max_length=30, choices=SERVICE_TYPE_CHOICES, default='OUTPATIENT')
    workflow_state = models.CharField(max_length=30, choices=WORKFLOW_STATE_CHOICES, default='OPEN')
    
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    total_claim_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_claim_copay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_claim_net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    payer_code = models.CharField(max_length=50, default='SHA')
    payer_name = models.CharField(max_length=255, default='Social Health Authority')
    
    interventions = models.JSONField(default=list, blank=True)
    diagnoses = models.JSONField(default=list, blank=True)
    line_items = models.JSONField(default=list, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    
    cancel_reason_type = models.CharField(max_length=100, blank=True, null=True)
    cancel_reason_text = models.TextField(blank=True, null=True)
    
    discharged_on = models.DateTimeField(blank=True, null=True)
    discharge_reason = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'DHA Virtual Claim'

    def __str__(self):
        return f"Claim {self.invoice_number or self.id} ({self.patient_name}) - {self.workflow_state}"


class DHAAuthorization(models.Model):
    """Authorizations record (OTP or Biometrics)."""

    facility_id = models.CharField(max_length=50, default='1')
    guid = models.CharField(max_length=255, unique=True)
    auth_code = models.CharField(max_length=100, blank=True, null=True)
    token = models.CharField(max_length=255, blank=True, null=True)
    patient_id = models.CharField(max_length=100)
    beneficiary_name = models.CharField(max_length=255, blank=True, null=True)
    beneficiary_number = models.CharField(max_length=100, blank=True, null=True)
    service_type = models.CharField(max_length=50, default='OUTPATIENT')
    authorization_type = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=50, default='ACTIVE')
    is_complete = models.BooleanField(default=False)
    needs_preauth = models.BooleanField(default=False)
    interventions = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, null=True)
    date_authorized = models.DateTimeField(blank=True, null=True)
    expiry = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'DHA Authorization'

    def __str__(self):
        return f"Auth {self.auth_code or self.guid} ({self.beneficiary_name}) - {self.status}"


class DHAPrescription(models.Model):
    """ePrescription and dispense history."""

    consent_token = models.CharField(max_length=255)
    guid = models.CharField(max_length=255, blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    doctor_review_status = models.CharField(max_length=50, default='APPROVED')
    status = models.CharField(max_length=50, default='ACTIVE')
    intervention_code = models.CharField(max_length=100)
    identification_number = models.CharField(max_length=100, blank=True, null=True)
    identification_type = models.CharField(max_length=50, blank=True, null=True)
    regulation_body = models.CharField(max_length=50, blank=True, null=True)
    items = models.JSONField(default=list, blank=True)
    dispenses = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'DHA Prescription'

    def __str__(self):
        return f"Prescription {self.code or self.id} ({self.status})"


class DHAEmergencyClaim(models.Model):
    """Emergency & EMT Case Claims."""

    consent_token = models.CharField(max_length=255, blank=True, null=True)
    reference_number = models.CharField(max_length=100)
    case_number = models.CharField(max_length=100, blank=True, null=True)
    brought_by = models.CharField(max_length=50, default='PARAMEDICS')
    identification_number = models.CharField(max_length=100, blank=True, null=True)
    identification_type = models.CharField(max_length=50, blank=True, null=True)
    beneficiary_cr_id = models.CharField(max_length=100, blank=True, null=True)
    mode_of_arrival = models.CharField(max_length=50, default='AMBULANCE')
    interventions = models.JSONField(default=list, blank=True)
    protocols = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, default='SUBMITTED')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'DHA Emergency Claim'

    def __str__(self):
        return f"Emergency Claim {self.reference_number} ({self.mode_of_arrival})"


class DHALog(models.Model):
    """
    Security Audit Trail: Logs all API communications sent to DHA AfyaConnect middleware.
    Sensitive tokens and authorization credentials are automatically masked.
    """

    facility_id = models.CharField(max_length=50, default='1')
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField(default=200)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)
    is_mocked = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'DHA Audit Log'

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.method} {self.endpoint} -> {self.status_code}"
