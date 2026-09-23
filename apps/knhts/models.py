from django.db import models


class KNHTSConcept(models.Model):
    """Kenya National Health Terminology Service concept catalog."""

    CODE_SYSTEM_CHOICES = (
        ('SNOMED-CT', 'SNOMED CT'),
        ('ICD-11', 'ICD-11'),
        ('LOINC', 'LOINC'),
        ('KNHTS', 'KNHTS'),
        ('CIEL', 'CIEL'),
        ('KEMSA-HPT', 'KEMSA Health Products & Technologies'),
        ('HL7-FHIR', 'HL7 FHIR'),
    )

    DOMAIN_CHOICES = (
        ('Diagnosis', 'Diagnosis'),
        ('Procedure', 'Procedure'),
        ('Medication', 'Medication'),
        ('Laboratory', 'Laboratory'),
        ('Observation', 'Observation'),
        ('Gender', 'Gender'),
        ('Finding', 'Finding'),
        ('Anatomy', 'Anatomy'),
    )

    code = models.CharField(max_length=100, unique=True)
    code_system = models.CharField(max_length=50, choices=CODE_SYSTEM_CHOICES, default='KNHTS')
    display = models.CharField(max_length=500)
    domain = models.CharField(max_length=50, choices=DOMAIN_CHOICES, default='Diagnosis')
    description = models.TextField(blank=True, null=True)
    synonyms = models.TextField(blank=True, null=True, help_text="Comma-separated synonym terms")
    parent_code = models.CharField(max_length=100, blank=True, null=True, help_text="Parent concept code")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code_system', 'code']
        verbose_name = 'KNHTS Concept'
        indexes = [
            models.Index(fields=['code_system', 'domain']),
            models.Index(fields=['display']),
        ]

    def __str__(self):
        return f"[{self.code_system}] {self.code} – {self.display}"


class MedicationHPT(models.Model):
    """KEMSA Health Products & Technologies (HPT) registry."""

    CATEGORY_CHOICES = (
        ('Essential Medicine', 'Essential Medicine'),
        ('Antiretroviral', 'Antiretroviral'),
        ('Vaccine', 'Vaccine'),
        ('Diagnostic', 'Diagnostic'),
        ('Medical Supply', 'Medical Supply'),
        ('Equipment', 'Equipment'),
    )

    FORM_CHOICES = (
        ('Tablet', 'Tablet'),
        ('Capsule', 'Capsule'),
        ('Syrup', 'Syrup'),
        ('Injection', 'Injection'),
        ('Cream', 'Cream'),
        ('Drops', 'Drops'),
        ('Inhaler', 'Inhaler'),
        ('Suppository', 'Suppository'),
        ('Powder', 'Powder'),
        ('Suspension', 'Suspension'),
        ('Other', 'Other'),
    )

    kemsa_code = models.CharField(max_length=50, unique=True, help_text="KEMSA/KNHTS drug code")
    generic_name = models.CharField(max_length=255)
    brand_names = models.CharField(max_length=500, blank=True, null=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Essential Medicine')
    dosage_form = models.CharField(max_length=50, choices=FORM_CHOICES, default='Tablet')
    strength = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., 500mg, 250mg/5ml")
    route_of_administration = models.CharField(max_length=100, blank=True, null=True)
    knhts_code = models.CharField(max_length=50, blank=True, null=True)
    snomed_code = models.CharField(max_length=50, blank=True, null=True)
    atc_code = models.CharField(max_length=50, blank=True, null=True, help_text="WHO ATC Classification code")
    is_on_essential_medicines_list = models.BooleanField(default=True)
    requires_prescription = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['generic_name']
        verbose_name = 'Medication / HPT Registry Entry'
        indexes = [
            models.Index(fields=['generic_name']),
            models.Index(fields=['kemsa_code']),
        ]

    def __str__(self):
        return f"[{self.kemsa_code}] {self.generic_name} {self.strength or ''} ({self.dosage_form})"


class TerminologyCatalog(models.Model):
    """Tracks the sync/update status of each external terminology catalog."""

    CATALOG_CHOICES = (
        ('SNOMED-CT', 'SNOMED CT'),
        ('ICD-11', 'ICD-11'),
        ('LOINC', 'LOINC'),
        ('KNHTS', 'KNHTS'),
        ('CIEL', 'CIEL'),
        ('KEMSA-HPT', 'KEMSA HPT'),
    )

    STATUS_CHOICES = (
        ('Active', 'Active'),
        ('Updating', 'Updating'),
        ('Error', 'Error'),
        ('Inactive', 'Inactive'),
    )

    catalog_name = models.CharField(max_length=50, choices=CATALOG_CHOICES, unique=True)
    version = models.CharField(max_length=50, default='2024')
    total_concepts = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    last_updated = models.DateTimeField(auto_now=True)
    source_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Terminology Catalog'

    def __str__(self):
        return f"{self.catalog_name} v{self.version} – {self.status} ({self.total_concepts} concepts)"
