from django.db import models

from core.models import BaseModel, Facility


class HieConnection(BaseModel):
	"""Per-facility Kenya HIE gateway connection state & maturity level."""

	STATUS_CHOICES = (
		('CONNECTED', 'Connected'),
		('DISCONNECTED', 'Disconnected'),
		('TESTING', 'Testing'),
		('ERROR', 'Error'),
	)

	facility = models.OneToOneField(Facility, on_delete=models.CASCADE, related_name='hie_connection')
	endpoint = models.URLField(default='https://hie.health.go.ke/api/v1/fhir')
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DISCONNECTED')
	latency_ms = models.PositiveIntegerField(default=0)
	maturity_level = models.PositiveSmallIntegerField(default=1)
	mfl_code = models.CharField(max_length=30, blank=True, default='')
	last_checked_at = models.DateTimeField(null=True, blank=True)

	def __str__(self):
		return f"HIE Connection - {self.facility.name}"


class TerminologyStandard(BaseModel):
	"""National/global medical terminology catalog synced into this facility's KNHTS mapping."""

	STATUS_CHOICES = (('ACTIVE', 'Active'), ('SYNCED', 'Synced'), ('PENDING', 'Pending'))

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='terminology_standards')
	code = models.CharField(max_length=20)
	name = models.CharField(max_length=255)
	description = models.TextField(blank=True)
	version = models.CharField(max_length=100, blank=True, default='')
	active_count = models.PositiveIntegerField(default=0)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

	class Meta:
		unique_together = ('facility', 'code')
		ordering = ['code']

	def __str__(self):
		return f"{self.code} - {self.facility.name}"


class QualityMeasure(BaseModel):
	"""Facility-level Kenya clinical quality indicator (ANC 4+, HTN control, TB screening, etc.)."""

	CATEGORY_CHOICES = (
		('Maternal & Child Health', 'Maternal & Child Health'),
		('Communicable Diseases', 'Communicable Diseases'),
		('Non-Communicable Diseases', 'Non-Communicable Diseases'),
		('Hospital Operational', 'Hospital Operational'),
	)
	STATUS_CHOICES = (('Compliant', 'Compliant'), ('At Risk', 'At Risk'), ('Needs Improvement', 'Needs Improvement'))

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='quality_measures')
	code = models.CharField(max_length=50)
	title = models.CharField(max_length=255)
	category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default='Hospital Operational')
	numerator_description = models.CharField(max_length=255, blank=True)
	denominator_description = models.CharField(max_length=255, blank=True)
	numerator_value = models.PositiveIntegerField(default=0)
	denominator_value = models.PositiveIntegerField(default=0)
	target_rate = models.DecimalField(max_digits=5, decimal_places=1, default=0)
	last_calculated = models.DateField(null=True, blank=True)

	class Meta:
		unique_together = ('facility', 'code')
		ordering = ['category', 'code']

	@property
	def calculated_rate(self):
		if not self.denominator_value:
			return 0.0
		return round((self.numerator_value / self.denominator_value) * 100, 1)

	@property
	def compliance_status(self):
		rate = self.calculated_rate
		if rate >= float(self.target_rate):
			return 'Compliant'
		if rate >= float(self.target_rate) * 0.8:
			return 'At Risk'
		return 'Needs Improvement'

	def __str__(self):
		return f"{self.code} - {self.facility.name}"


class HieSyncLog(BaseModel):
	"""Immutable audit trail of every Kenya HIE data exchange event for a facility."""

	TYPE_CHOICES = (
		('OUTBOUND_BUNDLE', 'Outbound FHIR Bundle'),
		('SURVEILLANCE_SDMX', 'Surveillance SDMX Export'),
		('QUALITY_MEASURE', 'Quality Measure Submission'),
		('PATIENT_PUSH', 'Patient Push'),
	)
	STATUS_CHOICES = (('SUCCESS', 'Success'), ('FAILED', 'Failed'), ('QUEUED', 'Queued'))

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='hie_sync_logs')
	log_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
	records_transferred = models.PositiveIntegerField(default=0)
	message = models.CharField(max_length=500, blank=True)
	payload_snippet = models.TextField(blank=True)

	class Meta:
		ordering = ['-created_at']
		indexes = [models.Index(fields=['facility', 'log_type'])]

	def __str__(self):
		return f"{self.log_type} - {self.facility.name} - {self.status}"
