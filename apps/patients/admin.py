from django.contrib import admin

from .models import EhrRecord, Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
	list_display = (
		'patient_id',
		'first_name',
		'last_name',
		'facility',
		'phone',
		'email',
		'is_active',
		'created_at',
	)
	list_filter = ('facility', 'gender', 'marital_status', 'blood_group', 'is_active')
	search_fields = ('patient_id', 'first_name', 'last_name', 'phone', 'email')
	ordering = ('-created_at',)


@admin.register(EhrRecord)
class EhrRecordAdmin(admin.ModelAdmin):
	list_display = ('id', 'patient', 'facility', 'date', 'doctor', 'diagnosis', 'is_active', 'created_at')
	list_filter = ('facility', 'is_active', 'date')
	search_fields = ('diagnosis', 'symptoms', 'treatment', 'doctor', 'doctor_notes', 'patient__patient_id')
	ordering = ('-date', '-created_at')
