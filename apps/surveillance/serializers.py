from rest_framework import serializers

from patients.models import Patient
from .models import IdsrWeeklyReport, NotifiableDiseaseAlert, PublicHealthEvent


class NotifiableDiseaseAlertSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    patientId = serializers.CharField(write_only=True, required=False, allow_blank=True)
    diseaseName = serializers.CharField(source='disease_name')
    icdCode = serializers.CharField(source='icd_code', required=False, allow_blank=True, default='')
    patientName = serializers.CharField(source='patient_name', required=False, allow_blank=True, default='')
    subCounty = serializers.CharField(source='sub_county', required=False, allow_blank=True, default='')
    detectedAt = serializers.DateTimeField(source='detected_at', read_only=True)
    mohNotified = serializers.BooleanField(source='moh_notified', read_only=True)
    mohNotificationTimestamp = serializers.DateTimeField(source='moh_notified_at', read_only=True)
    actionTaken = serializers.CharField(source='action_taken', required=False, allow_blank=True, default='')

    class Meta:
        model = NotifiableDiseaseAlert
        fields = [
            'id', 'facilityId', 'patientId', 'diseaseName', 'icdCode', 'urgency',
            'patientName', 'age', 'gender', 'subCounty', 'detectedAt', 'status',
            'mohNotified', 'mohNotificationTimestamp', 'actionTaken',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        patient_external_id = attrs.pop('patientId', None)
        facility_id = attrs.get('facility_id')

        if self.instance is None and facility_id is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        if patient_external_id:
            target_facility_id = facility_id if facility_id is not None else self.instance.facility_id
            patient = Patient.objects.filter(
                patient_id=patient_external_id,
                facility_id=target_facility_id,
                is_active=True,
            ).first()
            attrs['patient'] = patient

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id if instance.patient_id else ''
        return data


class IdsrWeeklyReportSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    epiWeek = serializers.IntegerField(source='epi_week')
    startDate = serializers.DateField(source='start_date')
    endDate = serializers.DateField(source='end_date')
    facilityMflCode = serializers.CharField(source='facility_mfl_code', required=False, allow_blank=True, default='')
    subCounty = serializers.CharField(source='sub_county', required=False, allow_blank=True, default='')
    county = serializers.CharField(source='county', required=False, allow_blank=True, default='')
    submissionDate = serializers.DateTimeField(source='submission_date', required=False, allow_null=True)
    submittedBy = serializers.CharField(source='submitted_by', required=False, allow_blank=True, default='')
    totalCasesSummary = serializers.IntegerField(source='total_cases_summary', required=False, default=0)
    totalDeathsSummary = serializers.IntegerField(source='total_deaths_summary', required=False, default=0)
    facilityName = serializers.SerializerMethodField()

    class Meta:
        model = IdsrWeeklyReport
        fields = [
            'id', 'facilityId', 'facilityName', 'epiWeek', 'year', 'startDate', 'endDate',
            'facilityMflCode', 'subCounty', 'county', 'status', 'submissionDate',
            'submittedBy', 'diseases', 'totalCasesSummary', 'totalDeathsSummary',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def get_facilityName(self, obj):
        return obj.facility.name if obj.facility_id else ''


class PublicHealthEventSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    eventName = serializers.CharField(source='event_name')
    eventType = serializers.CharField(source='event_type', required=False, default='OUTBREAK_CLUSTER')
    casesCount = serializers.IntegerField(source='cases_count', required=False, default=0)
    thresholdBreached = serializers.CharField(source='threshold_breached', required=False, allow_blank=True, default='')
    detectedDate = serializers.DateField(source='detected_date', read_only=True)
    alertLevel = serializers.CharField(source='alert_level', required=False, default='AMBER')
    responseStatus = serializers.CharField(source='response_status', required=False, default='ACTIVE')
    alertSentToCounties = serializers.BooleanField(source='alert_sent_to_counties', required=False, default=False)

    class Meta:
        model = PublicHealthEvent
        fields = [
            'id', 'facilityId', 'eventName', 'eventType', 'location', 'casesCount',
            'thresholdBreached', 'detectedDate', 'alertLevel', 'responseStatus',
            'alertSentToCounties', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'detectedDate', 'is_active', 'created_at', 'updated_at']
