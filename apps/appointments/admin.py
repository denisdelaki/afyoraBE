from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
	list_display = ('appointment_id', 'facility', 'patient', 'date', 'time', 'doctor', 'status')
	list_filter = ('facility', 'status', 'date', 'department')
	search_fields = ('appointment_id', 'patient__patient_id', 'patient__first_name', 'patient__last_name')
