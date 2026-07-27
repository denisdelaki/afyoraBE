from django.db import models

from core.models import BaseModel, Facility
from patients.models import Patient


class Appointment(BaseModel):
	STATUS_CHOICES = (
		('Scheduled', 'Scheduled'),
		('Confirmed', 'Confirmed'),
		('InProgress', 'In Progress'),
		('Completed', 'Completed'),
		('Cancelled', 'Cancelled'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='appointments',
	)
	patient = models.ForeignKey(
		Patient,
		on_delete=models.CASCADE,
		related_name='appointments',
	)
	appointment_id = models.CharField(max_length=30)
	date = models.DateField()
	time = models.TimeField()
	doctor = models.CharField(max_length=255)
	department = models.CharField(max_length=150)
	status = models.CharField(
		max_length=20,
		choices=STATUS_CHOICES,
		default='Scheduled',
	)

	class Meta:
		ordering = ['date', 'time', '-created_at']
		unique_together = ('facility', 'appointment_id')
		indexes = [
			models.Index(fields=['facility', 'appointment_id']),
			models.Index(fields=['facility', 'date']),
			models.Index(fields=['facility', 'status']),
			models.Index(fields=['facility', 'patient']),
		]

	def __str__(self):
		return f"{self.appointment_id} - {self.patient.patient_id}"
