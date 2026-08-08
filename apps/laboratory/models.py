from django.db import models

from core.models import BaseModel, Facility


class LabTest(BaseModel):
	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='lab_tests',
	)
	test_id = models.CharField(max_length=20)
	name = models.CharField(max_length=255)
	category = models.CharField(max_length=100)
	duration = models.CharField(max_length=50)
	price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

	class Meta:
		ordering = ['name']
		unique_together = ('facility', 'test_id')
		indexes = [
			models.Index(fields=['facility', 'test_id']),
			models.Index(fields=['facility', 'name']),
			models.Index(fields=['facility', 'category']),
		]

	def __str__(self):
		return f"{self.test_id} - {self.name}"


class LabRequest(BaseModel):
	STATUS_CHOICES = (
		('Pending', 'Pending'),
		('In Progress', 'In Progress'),
		('Completed', 'Completed'),
		('Approved', 'Approved'),
	)

	PRIORITY_CHOICES = (
		('Routine', 'Routine'),
		('Urgent', 'Urgent'),
		('STAT', 'STAT'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='lab_requests',
	)
	request_id = models.CharField(max_length=20)
	patient = models.CharField(max_length=255)
	patient_id = models.CharField(max_length=30)
	test = models.ForeignKey(
		LabTest,
		on_delete=models.PROTECT,
		related_name='requests',
	)
	ordered_by_employee_id = models.CharField(max_length=50)
	ordered_by = models.CharField(max_length=150)
	order_date = models.DateField()
	sample_collected = models.CharField(max_length=50, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
	priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Routine')
	notes = models.TextField(blank=True)

	class Meta:
		ordering = ['-order_date', '-created_at']
		unique_together = ('facility', 'request_id')
		indexes = [
			models.Index(fields=['facility', 'request_id']),
			models.Index(fields=['facility', 'status']),
			models.Index(fields=['facility', 'order_date']),
			models.Index(fields=['facility', 'patient_id']),
		]

	def __str__(self):
		return f"{self.request_id} - {self.patient}"


class LabResult(BaseModel):
	STATUS_CHOICES = (
		('Awaiting Approval', 'Awaiting Approval'),
		('Approved', 'Approved'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='lab_results',
	)
	lab_id = models.CharField(max_length=20)
	request = models.OneToOneField(
		LabRequest,
		on_delete=models.CASCADE,
		related_name='result',
	)
	parameters = models.JSONField(default=list, blank=True)
	technician = models.CharField(max_length=150)
	completed_date = models.DateField()
	approved_by = models.CharField(max_length=150, null=True, blank=True)
	status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Awaiting Approval')
	remarks = models.TextField(blank=True)

	class Meta:
		ordering = ['-completed_date', '-created_at']
		unique_together = ('facility', 'lab_id')
		indexes = [
			models.Index(fields=['facility', 'lab_id']),
			models.Index(fields=['facility', 'status']),
			models.Index(fields=['facility', 'completed_date']),
		]

	def __str__(self):
		return f"{self.lab_id} - {self.request.patient}"
