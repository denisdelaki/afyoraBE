from django.contrib import admin

from .models import EhrRecord, OutpatientTicket, OutpatientTicketMovement, Patient


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


class OutpatientTicketMovementInline(admin.TabularInline):
	model = OutpatientTicketMovement
	extra = 0
	readonly_fields = ('created_at',)


@admin.register(OutpatientTicket)
class OutpatientTicketAdmin(admin.ModelAdmin):
	list_display = ('ticket_number', 'patient', 'facility', 'destination', 'assigned_to', 'status', 'created_at')
	list_filter = ('facility', 'destination', 'status')
	search_fields = ('ticket_number', 'patient__patient_id', 'patient__first_name', 'patient__last_name')
	readonly_fields = ('ticket_number', 'created_by', 'called_by', 'completed_at', 'created_at', 'updated_at')
	inlines = (OutpatientTicketMovementInline,)
