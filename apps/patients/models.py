from django.db import models

from core.models import BaseModel, Facility


class Patient(BaseModel):
	GENDER_CHOICES = (
		('male', 'Male'),
		('female', 'Female'),
		('other', 'Other'),
		('prefer_not_to_say', 'Prefer not to say'),
	)

	MARITAL_STATUS_CHOICES = (
		('single', 'Single'),
		('married', 'Married'),
		('divorced', 'Divorced'),
		('widowed', 'Widowed'),
		('other', 'Other'),
	)

	BLOOD_GROUP_CHOICES = (
		('A+', 'A+'),
		('A-', 'A-'),
		('B+', 'B+'),
		('B-', 'B-'),
		('AB+', 'AB+'),
		('AB-', 'AB-'),
		('O+', 'O+'),
		('O-', 'O-'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='patients',
	)
	patient_id = models.CharField(max_length=20)
	first_name = models.CharField(max_length=150)
	last_name = models.CharField(max_length=150)
	gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
	date_of_birth = models.DateField(null=True, blank=True)
	age = models.PositiveIntegerField(null=True, blank=True)
	phone = models.CharField(max_length=20, blank=True)
	email = models.EmailField(blank=True)
	address = models.TextField(blank=True)
	city = models.CharField(max_length=100, blank=True)
	marital_status = models.CharField(
		max_length=20,
		choices=MARITAL_STATUS_CHOICES,
		blank=True,
	)
	blood_group = models.CharField(
		max_length=3,
		choices=BLOOD_GROUP_CHOICES,
		blank=True,
	)
	emergency_contact_name = models.CharField(max_length=150, blank=True)
	emergency_contact_phone = models.CharField(max_length=20, blank=True)
	allergies = models.TextField(blank=True)
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ['-created_at']
		unique_together = ('facility', 'patient_id')
		indexes = [
			models.Index(fields=['facility', 'patient_id']),
			models.Index(fields=['facility', 'first_name']),
			models.Index(fields=['facility', 'last_name']),
			models.Index(fields=['facility', 'phone']),
		]

	def __str__(self):
		return f"{self.patient_id} - {self.first_name} {self.last_name}"


class PatientVisit(BaseModel):
	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='patient_visits',
	)
	patient = models.ForeignKey(
		Patient,
		on_delete=models.CASCADE,
		related_name='visits',
	)
	visit_date = models.DateField()
	served_by = models.CharField(max_length=150)
	diagnosis = models.CharField(max_length=255, blank=True)
	prescription_record = models.ForeignKey(
		'pharmacy.Prescription',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='visit_histories',
	)
	prescription = models.CharField(max_length=255, blank=True)
	prescriptions = models.JSONField(default=list, blank=True)
	what_happened = models.TextField(blank=True)
	amount_billed = models.DecimalField(max_digits=10, decimal_places=2, default=0)

	class Meta:
		ordering = ['-visit_date', '-created_at']
		indexes = [
			models.Index(fields=['facility', 'patient', 'visit_date']),
			models.Index(fields=['facility', 'visit_date']),
		]

	def __str__(self):
		return f"Visit {self.id} - {self.patient.patient_id} on {self.visit_date}"


class EhrRecord(BaseModel):
	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='ehr_records',
	)
	patient = models.ForeignKey(
		Patient,
		on_delete=models.CASCADE,
		related_name='ehr_records',
	)
	date = models.DateField(auto_now_add=True)
	doctor = models.CharField(max_length=150)
	diagnosis = models.CharField(max_length=255)
	symptoms = models.TextField(blank=True)
	treatment = models.TextField(blank=True)
	doctor_notes = models.TextField(blank=True)

	class Meta:
		ordering = ['-date', '-created_at']
		indexes = [
			models.Index(fields=['facility', 'patient', 'date']),
			models.Index(fields=['facility', 'date']),
		]

	def __str__(self):
		return f"EHR {self.id} - {self.patient.patient_id} on {self.date}"
