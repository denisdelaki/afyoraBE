from django.db import models

from core.models import BaseModel, Facility


class DrugCategory(BaseModel):
	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='drug_categories',
	)
	name = models.CharField(max_length=255)
	description = models.TextField(blank=True)

	class Meta:
		ordering = ['name']
		unique_together = ('facility', 'name')
		indexes = [
			models.Index(fields=['facility', 'name']),
		]

	def __str__(self):
		return f"{self.name}"


class Drug(BaseModel):
	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='drugs',
	)
	drug_id = models.CharField(max_length=20)
	name = models.CharField(max_length=255)
	category = models.ForeignKey(
		'DrugCategory',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='drugs'
	)
	stock = models.PositiveIntegerField(default=0)
	min_stock = models.PositiveIntegerField(default=0)
	price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	expiry_date = models.DateField(null=True, blank=True)
	manufacturer = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ['-created_at']
		unique_together = ('facility', 'drug_id')
		indexes = [
			models.Index(fields=['facility', 'drug_id']),
			models.Index(fields=['facility', 'name']),
			models.Index(fields=['facility', 'category']),
			models.Index(fields=['facility', 'is_active']),
		]

	def __str__(self):
		return f"{self.drug_id} - {self.name}"


class Prescription(BaseModel):
	STATUS_CHOICES = (
		('Pending', 'Pending'),
		('Dispensed', 'Dispensed'),
		('Cancelled', 'Cancelled'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='prescriptions',
	)
	prescription_id = models.CharField(max_length=20)
	patient_id = models.CharField(max_length=30)
	doctor_id = models.CharField(max_length=30)
	drugs = models.JSONField(default=list, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
	date = models.DateField()

	class Meta:
		ordering = ['-date', '-created_at']
		unique_together = ('facility', 'prescription_id')
		indexes = [
			models.Index(fields=['facility', 'prescription_id']),
			models.Index(fields=['facility', 'status']),
			models.Index(fields=['facility', 'date']),
			models.Index(fields=['facility', 'patient_id']),
		]

	def __str__(self):
		return f"{self.prescription_id} - {self.patient_id}"
