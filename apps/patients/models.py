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


class OutpatientTicket(BaseModel):
	"""The patient's current place in the outpatient workflow."""

	DESTINATION_CHOICES = (
		('reception', 'Reception'),
		('consultation', 'Consultation'),
		('laboratory', 'Laboratory'),
		('radiology', 'Radiology'),
		('pharmacy', 'Pharmacy'),
		('billing', 'Billing'),
	)
	STATUS_CHOICES = (
		('waiting', 'Waiting'),
		('called', 'Called'),
		('completed', 'Completed'),
	)

	facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='outpatient_tickets')
	patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='outpatient_tickets')
	ticket_number = models.CharField(max_length=30)
	destination = models.CharField(max_length=20, choices=DESTINATION_CHOICES, default='consultation')
	assigned_to = models.ForeignKey(
		'core.User', on_delete=models.SET_NULL, null=True, blank=True,
		related_name='assigned_outpatient_tickets',
	)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
	created_by = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, related_name='created_outpatient_tickets')
	called_by = models.ForeignKey(
		'core.User', on_delete=models.SET_NULL, null=True, blank=True,
		related_name='called_outpatient_tickets',
	)
	notes = models.TextField(blank=True)
	completed_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ['created_at']
		unique_together = ('facility', 'ticket_number')
		indexes = [
			models.Index(fields=['facility', 'destination', 'status', 'created_at']),
			models.Index(fields=['facility', 'patient', 'status']),
		]

	def __str__(self):
		return f"{self.ticket_number} - {self.patient}"


class OutpatientTicketMovement(models.Model):
	"""An immutable record of every hand-off made for a ticket."""

	ticket = models.ForeignKey(OutpatientTicket, on_delete=models.CASCADE, related_name='movements')
	from_destination = models.CharField(max_length=20, choices=OutpatientTicket.DESTINATION_CHOICES, blank=True)
	to_destination = models.CharField(max_length=20, choices=OutpatientTicket.DESTINATION_CHOICES)
	forwarded_by = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, related_name='ticket_forwards')
	assigned_to = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_assignments')
	notes = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['created_at']


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
