from django.db import models

from core.models import BaseModel, Facility
from patients.models import Patient


class NotifiableDiseaseAlert(BaseModel):
	"""Real-time MOH outbreak notification (Cholera, Measles, Anthrax, etc.)."""

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='disease_alerts')
	patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name='disease_alerts')
	disease_name = models.CharField(max_length=255)
	icd_code = models.CharField(max_length=20, blank=True, default='')
	urgency = models.CharField(max_length=20, default='HIGH')
	patient_name = models.CharField(max_length=255, blank=True)
	age = models.PositiveIntegerField(null=True, blank=True)
	gender = models.CharField(max_length=20, blank=True)
	sub_county = models.CharField(max_length=150, blank=True)
	detected_at = models.DateTimeField(auto_now_add=True)
	status = models.CharField(max_length=20, default='TRIGGERED')
	moh_notified = models.BooleanField(default=False)
	moh_notified_at = models.DateTimeField(null=True, blank=True)
	action_taken = models.TextField(blank=True)

	class Meta:
		ordering = ['-detected_at']
		indexes = [models.Index(fields=['facility', 'status'])]

	def __str__(self):
		return f"{self.disease_name} alert - {self.patient_name}"


class IdsrWeeklyReport(BaseModel):
	"""IDSR Form 504 weekly case & mortality aggregation."""

	STATUS_CHOICES = (('DRAFT', 'Draft'), ('SUBMITTED', 'Submitted'), ('VERIFIED', 'Verified'))

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='idsr_weekly_reports')
	epi_week = models.PositiveSmallIntegerField()
	year = models.PositiveSmallIntegerField()
	start_date = models.DateField()
	end_date = models.DateField()
	facility_mfl_code = models.CharField(max_length=30, blank=True, default='')
	sub_county = models.CharField(max_length=150, blank=True)
	county = models.CharField(max_length=150, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
	submission_date = models.DateTimeField(null=True, blank=True)
	submitted_by = models.CharField(max_length=150, blank=True)
	khis_submission_id = models.CharField(max_length=50, blank=True, default='')
	diseases = models.JSONField(default=list, blank=True)
	total_cases_summary = models.PositiveIntegerField(default=0)
	total_deaths_summary = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['-year', '-epi_week']
		unique_together = ('facility', 'year', 'epi_week')
		indexes = [models.Index(fields=['facility', 'year', 'epi_week'])]

	def __str__(self):
		return f"IDSR 504 - Week {self.epi_week}/{self.year} - {self.facility_id}"


class PublicHealthEvent(BaseModel):
	"""Outbreak cluster / threshold breach detected via public health surveillance."""

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='public_health_events')
	event_name = models.CharField(max_length=255)
	event_type = models.CharField(max_length=40, default='OUTBREAK_CLUSTER')
	location = models.CharField(max_length=255, blank=True)
	cases_count = models.PositiveIntegerField(default=0)
	threshold_breached = models.CharField(max_length=255, blank=True)
	detected_date = models.DateField(auto_now_add=True)
	alert_level = models.CharField(max_length=20, default='AMBER')
	response_status = models.CharField(max_length=30, default='ACTIVE')
	alert_sent_to_counties = models.BooleanField(default=False)

	class Meta:
		ordering = ['-detected_date', '-created_at']
		indexes = [models.Index(fields=['facility', 'alert_level'])]

	def __str__(self):
		return f"{self.event_name} ({self.alert_level})"
