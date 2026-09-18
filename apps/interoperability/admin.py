from django.contrib import admin

from .models import HieConnection, HieSyncLog, QualityMeasure, TerminologyStandard


@admin.register(HieConnection)
class HieConnectionAdmin(admin.ModelAdmin):
	list_display = ('facility', 'status', 'latency_ms', 'maturity_level', 'last_checked_at')
	list_filter = ('status', 'maturity_level')


@admin.register(TerminologyStandard)
class TerminologyStandardAdmin(admin.ModelAdmin):
	list_display = ('code', 'facility', 'status', 'active_count')
	list_filter = ('facility', 'status')
	search_fields = ('code', 'name')


@admin.register(QualityMeasure)
class QualityMeasureAdmin(admin.ModelAdmin):
	list_display = ('code', 'facility', 'category', 'numerator_value', 'denominator_value', 'target_rate')
	list_filter = ('facility', 'category')
	search_fields = ('code', 'title')


@admin.register(HieSyncLog)
class HieSyncLogAdmin(admin.ModelAdmin):
	list_display = ('facility', 'log_type', 'status', 'records_transferred', 'created_at')
	list_filter = ('facility', 'log_type', 'status')
