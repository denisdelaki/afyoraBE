from django.contrib import admin

from .models import IdsrWeeklyReport, NotifiableDiseaseAlert, PublicHealthEvent


@admin.register(NotifiableDiseaseAlert)
class NotifiableDiseaseAlertAdmin(admin.ModelAdmin):
	list_display = ('id', 'facility', 'disease_name', 'urgency', 'status', 'moh_notified', 'detected_at')
	list_filter = ('facility', 'urgency', 'status', 'moh_notified')
	search_fields = ('disease_name', 'patient_name', 'sub_county')


@admin.register(IdsrWeeklyReport)
class IdsrWeeklyReportAdmin(admin.ModelAdmin):
	list_display = ('id', 'facility', 'epi_week', 'year', 'status', 'total_cases_summary', 'total_deaths_summary')
	list_filter = ('facility', 'status', 'year')
	search_fields = ('sub_county', 'county', 'facility_mfl_code')


@admin.register(PublicHealthEvent)
class PublicHealthEventAdmin(admin.ModelAdmin):
	list_display = ('id', 'facility', 'event_name', 'alert_level', 'response_status', 'detected_date')
	list_filter = ('facility', 'alert_level', 'response_status')
	search_fields = ('event_name', 'location')
