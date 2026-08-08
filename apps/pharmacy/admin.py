from django.contrib import admin

from .models import Drug, Prescription


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
	list_display = (
		'drug_id',
		'name',
		'category',
		'stock',
		'min_stock',
		'price',
		'facility',
		'is_active',
	)
	list_filter = ('category', 'is_active', 'facility')
	search_fields = ('drug_id', 'name', 'manufacturer')


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
	list_display = (
		'prescription_id',
		'patient_id',
		'doctor_id',
		'status',
		'date',
		'facility',
		'is_active',
	)
	list_filter = ('status', 'date', 'facility', 'is_active')
	search_fields = ('prescription_id', 'patient_id', 'doctor_id')
