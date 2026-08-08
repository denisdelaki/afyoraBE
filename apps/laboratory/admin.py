from django.contrib import admin

from .models import LabRequest, LabResult, LabTest


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
	list_display = ('test_id', 'name', 'category', 'facility', 'price', 'is_active')
	search_fields = ('test_id', 'name', 'category', 'facility__name')
	list_filter = ('facility', 'category', 'is_active')


@admin.register(LabRequest)
class LabRequestAdmin(admin.ModelAdmin):
	list_display = (
		'request_id',
		'patient',
		'patient_id',
		'test',
		'facility',
		'status',
		'priority',
		'is_active',
	)
	search_fields = ('request_id', 'patient', 'patient_id', 'ordered_by', 'ordered_by_employee_id')
	list_filter = ('facility', 'status', 'priority', 'is_active')


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
	list_display = ('lab_id', 'request', 'facility', 'status', 'technician', 'completed_date', 'is_active')
	search_fields = ('lab_id', 'request__patient', 'request__patient_id', 'technician')
	list_filter = ('facility', 'status', 'is_active')
