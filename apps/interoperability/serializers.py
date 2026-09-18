from rest_framework import serializers

from .models import HieConnection, HieSyncLog, QualityMeasure, TerminologyStandard


MATURITY_LEVEL_DEFINITIONS = [
    {
        'level': 1,
        'title': 'Level 1: Unstructured Data Exchange',
        'subtitle': 'Basic document sharing',
        'description': 'Supports patient summaries, PDF discharge letters, and document exports.',
        'standards': ['PDF', 'Printed Summaries', 'Plain Text'],
    },
    {
        'level': 2,
        'title': 'Level 2: Structured Data Exchange',
        'subtitle': 'Formatted structured payloads',
        'description': 'Exchange structured CSV, XML, and JSON data schemas.',
        'standards': ['CSV', 'XML', 'REST JSON'],
    },
    {
        'level': 3,
        'title': 'Level 3: Semantic Interoperability',
        'subtitle': 'Standardized terminology & FHIR schemas',
        'description': 'Full FHIR R4/R4B exchange integrated with KNHTS, ICD-11, SNOMED CT, and LOINC.',
        'standards': ['FHIR R4', 'KNHTS', 'ICD-11', 'SNOMED CT', 'LOINC'],
    },
    {
        'level': 4,
        'title': 'Level 4: Automated Data Sharing',
        'subtitle': 'Real-time workflows & decision synchronization',
        'description': 'Automated real-time bidirectional data sharing, webhooks, and CDS rule exchange.',
        'standards': ['Kenya HIE Real-Time REST/FHIR', 'Webhooks', 'SDMX-HD'],
    },
]

TERMINOLOGY_STANDARD_SEED = [
    {'code': 'KNHTS', 'name': 'Kenya National Health Terminology Service', 'description': 'Official master terminology service for health classification in Kenya.', 'version': '2026.1 Release', 'active_count': 48290, 'status': 'ACTIVE'},
    {'code': 'ICD-11', 'name': 'International Classification of Diseases (11th Revision)', 'description': 'WHO standard for mortality and morbidity statistics.', 'version': '2025-01 WHO Release', 'active_count': 35100, 'status': 'SYNCED'},
    {'code': 'SNOMED-CT', 'name': 'Systematized Nomenclature of Medicine - Clinical Terms', 'description': 'Comprehensive clinical terminology system for diagnoses, procedures, and concepts.', 'version': 'US/International 2026', 'active_count': 125000, 'status': 'ACTIVE'},
    {'code': 'LOINC', 'name': 'Logical Observation Identifiers Names and Codes', 'description': 'Standard terminology for lab tests, vital signs, and clinical measurements.', 'version': 'v2.78', 'active_count': 18400, 'status': 'ACTIVE'},
    {'code': 'CIEL', 'name': 'Columbia International eHealth Laboratory Concept Dictionary', 'description': 'Interface terminology map for primary care and global health.', 'version': '2025-10', 'active_count': 56000, 'status': 'ACTIVE'},
    {'code': 'KEMSA-HPT', 'name': 'KEMSA / PPB Drug & Medical Supply Catalog', 'description': 'Kenya national registry of authorized medicines and medical devices.', 'version': '2026 Master Catalog', 'active_count': 9400, 'status': 'ACTIVE'},
]

QUALITY_MEASURE_SEED = [
    {'code': 'MCH-ANC-04', 'title': 'Antenatal Care 4+ Visits Rate', 'category': 'Maternal & Child Health', 'numerator_description': 'Pregnant women completing at least 4 ANC visits before delivery', 'denominator_description': 'Total pregnant women registered in facility catchment area', 'numerator_value': 0, 'denominator_value': 0, 'target_rate': 85.0},
    {'code': 'NCD-HTN-CTRL', 'title': 'Hypertension Blood Pressure Control Rate', 'category': 'Non-Communicable Diseases', 'numerator_description': 'Adult hypertensive patients with SBP < 140 and DBP < 90 mmHg on latest visit', 'denominator_description': 'Total active registered hypertensive patients', 'numerator_value': 0, 'denominator_value': 0, 'target_rate': 80.0},
    {'code': 'CD-TB-SCRN', 'title': 'Routine TB Screening Rate among Outpatients', 'category': 'Communicable Diseases', 'numerator_description': 'Outpatient encounters screened using Kenya 4-item TB symptom checklist', 'denominator_description': 'Total outpatient encounters', 'numerator_value': 0, 'denominator_value': 0, 'target_rate': 90.0},
    {'code': 'IMM-PENTA-03', 'title': 'Pentavalent 3 Immunization Coverage Rate', 'category': 'Maternal & Child Health', 'numerator_description': 'Infants receiving 3rd dose of Pentavalent vaccine by 14 weeks', 'denominator_description': 'Total surviving infants surviving to 14 weeks', 'numerator_value': 0, 'denominator_value': 0, 'target_rate': 95.0},
]


class HieConnectionSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    latencyMs = serializers.IntegerField(source='latency_ms', read_only=True)
    hieEndpoint = serializers.CharField(source='endpoint')
    maturityLevel = serializers.IntegerField(source='maturity_level', read_only=True)
    mflCode = serializers.CharField(source='mfl_code', read_only=True)
    lastCheckedAt = serializers.DateTimeField(source='last_checked_at', read_only=True)

    class Meta:
        model = HieConnection
        fields = ['facilityId', 'hieEndpoint', 'status', 'latencyMs', 'maturityLevel', 'mflCode', 'lastCheckedAt']


class TerminologyStandardSerializer(serializers.ModelSerializer):
    activeCount = serializers.IntegerField(source='active_count')

    class Meta:
        model = TerminologyStandard
        fields = ['id', 'code', 'name', 'description', 'version', 'activeCount', 'status']


class QualityMeasureSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    numeratorDescription = serializers.CharField(source='numerator_description', required=False, allow_blank=True)
    denominatorDescription = serializers.CharField(source='denominator_description', required=False, allow_blank=True)
    numeratorValue = serializers.IntegerField(source='numerator_value', required=False, default=0)
    denominatorValue = serializers.IntegerField(source='denominator_value', required=False, default=0)
    calculatedRate = serializers.FloatField(source='calculated_rate', read_only=True)
    targetRate = serializers.DecimalField(source='target_rate', max_digits=5, decimal_places=1, required=False)
    status = serializers.CharField(source='compliance_status', read_only=True)
    lastCalculated = serializers.DateField(source='last_calculated', required=False, allow_null=True)

    class Meta:
        model = QualityMeasure
        fields = [
            'id', 'facilityId', 'code', 'title', 'category', 'numeratorDescription', 'denominatorDescription',
            'numeratorValue', 'denominatorValue', 'calculatedRate', 'targetRate', 'status', 'lastCalculated',
        ]
        read_only_fields = ['id']


class HieSyncLogSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    timestamp = serializers.DateTimeField(source='created_at', read_only=True)
    type = serializers.CharField(source='log_type')
    recordsTransferred = serializers.IntegerField(source='records_transferred', required=False, default=0)
    payloadSnippet = serializers.CharField(source='payload_snippet', required=False, allow_blank=True)

    class Meta:
        model = HieSyncLog
        fields = ['id', 'facilityId', 'timestamp', 'type', 'status', 'recordsTransferred', 'message', 'payloadSnippet']
        read_only_fields = ['id', 'timestamp']
