from django.contrib import admin
from .models import KNHTSConcept, MedicationHPT, TerminologyCatalog


@admin.register(KNHTSConcept)
class KNHTSConceptAdmin(admin.ModelAdmin):
    list_display = ['code', 'code_system', 'domain', 'display', 'is_active', 'updated_at']
    list_filter = ['code_system', 'domain', 'is_active']
    search_fields = ['code', 'display', 'synonyms']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(MedicationHPT)
class MedicationHPTAdmin(admin.ModelAdmin):
    list_display = ['kemsa_code', 'generic_name', 'dosage_form', 'strength', 'category', 'is_on_essential_medicines_list', 'is_active']
    list_filter = ['category', 'dosage_form', 'is_on_essential_medicines_list', 'requires_prescription', 'is_active']
    search_fields = ['kemsa_code', 'generic_name', 'brand_names', 'atc_code']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TerminologyCatalog)
class TerminologyCatalogAdmin(admin.ModelAdmin):
    list_display = ['catalog_name', 'version', 'total_concepts', 'status', 'last_updated']
    list_filter = ['status', 'catalog_name']
    readonly_fields = ['last_updated']
