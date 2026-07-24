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
