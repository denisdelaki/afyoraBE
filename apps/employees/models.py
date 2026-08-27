from django.db import models
from core.models import BaseModel, Facility, FacilityRole


class Employee(BaseModel):
	"""Employee profile scoped to a facility (multi-tenant safe)."""

	STATUS_CHOICES = (
		('Active', 'Active'),
		('Inactive', 'Inactive'),
		('Terminated', 'Terminated'),
	)

	SHIFT_CHOICES = (
		('Morning', 'Morning'),
		('Evening', 'Evening'),
		('Night', 'Night'),
	)

	facility = models.ForeignKey(
		Facility,
		on_delete=models.CASCADE,
		related_name='employees'
	)
	employee_id = models.CharField(max_length=20)
	name = models.CharField(max_length=255)
	role = models.CharField(max_length=100)
	department = models.CharField(max_length=100, blank=True)
	email = models.EmailField(blank=True)
	phone = models.CharField(max_length=20, blank=True)
	join_date = models.DateField()
	salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
	shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, default='Morning')

	# Dynamic role assigned by facility_admin for permission-based access control.
	# Nullable — employees without a custom_role fall back to static role-based access.
	custom_role = models.ForeignKey(
		FacilityRole,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='employees',
	)

	class Meta:
		ordering = ['-created_at']
		unique_together = ('facility', 'employee_id')
		indexes = [
			models.Index(fields=['facility', 'employee_id']),
			models.Index(fields=['facility', 'email']),
			models.Index(fields=['facility', 'name']),
		]

	def __str__(self):
		return f"{self.employee_id} - {self.name}"
