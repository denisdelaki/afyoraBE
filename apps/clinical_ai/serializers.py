from rest_framework import serializers
from clinical_ai.models import (
    ClinicalAIConsultation,
    ClinicalAIRecommendation,
    ClinicalAIFeedback,
    ClinicalAIAuditEvent,
    ClinicalAIModelVersion,
)


class ClinicalSymptomsField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            return [item.strip() for item in data if item.strip()]
        raise serializers.ValidationError('Expected a string or a list of strings.')

    def to_representation(self, value):
        return value


class ClinicalAIConsultationRequestSerializer(serializers.Serializer):
    patient_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    consultation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    chief_complaint = serializers.CharField(required=False, allow_blank=True, default="")
    symptoms = ClinicalSymptomsField(required=False, default="")
    vitals = serializers.DictField(required=False, default=dict)
    laboratory_results = serializers.ListField(required=False, default=list)
    imaging_reports = serializers.ListField(required=False, default=list)
    pregnancy_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_pregnant = serializers.BooleanField(required=False, allow_null=True, default=None)
    breastfeeding = serializers.BooleanField(required=False, allow_null=True)
    observations = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, default=list)
    weight_kg = serializers.FloatField(required=False, allow_null=True)
    renal_function = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hepatic_function = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_vitals(self, value):
        if any(isinstance(item, bool) or not isinstance(item, (int, float, str, type(None))) for item in value.values()):
            raise serializers.ValidationError('Vital signs must be numbers, strings, or null.')
        return value

    def validate_laboratory_results(self, value):
        if any(not isinstance(item, (str, dict)) for item in value):
            raise serializers.ValidationError('Results must be strings or objects.')
        return value

    def validate_imaging_reports(self, value):
        return self.validate_laboratory_results(value)

    def validate(self, attrs):
        if attrs.get('is_pregnant') is None:
            pregnancy_status = str(attrs.get('pregnancy_status') or '').strip().lower()
            if pregnancy_status in ('yes', 'true', 'pregnant'):
                attrs['is_pregnant'] = True
            elif pregnancy_status in ('no', 'false', 'not pregnant'):
                attrs['is_pregnant'] = False
            else:
                raise serializers.ValidationError({
                    'is_pregnant': 'Provide an explicit pregnancy status as a boolean.'
                })
        return attrs

    def to_internal_value(self, data):
        data_dict = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'patient_id' not in data_dict and 'patientId' in data_dict:
            data_dict['patient_id'] = str(data_dict['patientId'])
        if 'consultation_id' not in data_dict and 'consultationId' in data_dict:
            data_dict['consultation_id'] = str(data_dict['consultationId'])
        if 'chief_complaint' not in data_dict and 'chiefComplaint' in data_dict:
            data_dict['chief_complaint'] = str(data_dict['chiefComplaint'])
        if 'pregnancy_status' not in data_dict and 'pregnancyStatus' in data_dict:
            data_dict['pregnancy_status'] = str(data_dict['pregnancyStatus'])
        if 'is_pregnant' not in data_dict and 'isPregnant' in data_dict:
            data_dict['is_pregnant'] = data_dict['isPregnant']
        if 'weight_kg' not in data_dict and 'weightKg' in data_dict:
            data_dict['weight_kg'] = data_dict['weightKg']
        if 'renal_function' not in data_dict and 'renalFunction' in data_dict:
            data_dict['renal_function'] = str(data_dict['renalFunction'])
        if 'hepatic_function' not in data_dict and 'hepaticFunction' in data_dict:
            data_dict['hepatic_function'] = str(data_dict['hepaticFunction'])
        if 'laboratory_results' not in data_dict and 'laboratoryResults' in data_dict:
            data_dict['laboratory_results'] = data_dict['laboratoryResults']
        if 'laboratory_results' not in data_dict and 'labs' in data_dict:
            data_dict['laboratory_results'] = data_dict['labs']
        if 'imaging_reports' not in data_dict and 'imagingReports' in data_dict:
            data_dict['imaging_reports'] = data_dict['imagingReports']
        if 'imaging_reports' not in data_dict and 'radiology' in data_dict:
            data_dict['imaging_reports'] = data_dict['radiology']

        ret = super().to_internal_value(data_dict)
        if not ret.get('patient_id'):
            raise serializers.ValidationError({'patient_id': 'Patient ID (or patientId) is required.'})
        return ret


class ClinicalAIFeedbackSerializer(serializers.Serializer):
    consultation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    recommendation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    action = serializers.ChoiceField(choices=['accepted', 'rejected', 'modified'], required=True)
    rating = serializers.IntegerField(required=False, min_value=1, max_value=5, allow_null=True)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")
    modified_value = serializers.JSONField(required=False, allow_null=True)

    def to_internal_value(self, data):
        data_dict = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'consultation_id' not in data_dict and 'consultationId' in data_dict:
            data_dict['consultation_id'] = str(data_dict['consultationId'])
        if 'recommendation_id' not in data_dict and 'recommendationId' in data_dict:
            data_dict['recommendation_id'] = str(data_dict['recommendationId'])
        if 'modified_value' not in data_dict and 'modifiedValue' in data_dict:
            data_dict['modified_value'] = data_dict['modifiedValue']
        ret = super().to_internal_value(data_dict)
        if not ret.get('consultation_id'):
            raise serializers.ValidationError({'consultation_id': 'consultation_id (or consultationId) is required.'})
        return ret


class ClinicalAIPrescriptionApprovalSerializer(serializers.Serializer):
    consultation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    recommendation_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    patient_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    drugs = serializers.ListField(child=serializers.DictField(), required=True)
    is_modified = serializers.BooleanField(required=False, default=False)
    modification_notes = serializers.CharField(required=False, allow_blank=True, default="")

    def to_internal_value(self, data):
        data_dict = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'consultation_id' not in data_dict and 'consultationId' in data_dict:
            data_dict['consultation_id'] = str(data_dict['consultationId'])
        if 'recommendation_id' not in data_dict and 'recommendationId' in data_dict:
            data_dict['recommendation_id'] = str(data_dict['recommendationId'])
        if 'patient_id' not in data_dict and 'patientId' in data_dict:
            data_dict['patient_id'] = str(data_dict['patientId'])
        if 'is_modified' not in data_dict and 'isModified' in data_dict:
            data_dict['is_modified'] = bool(data_dict['isModified'])
        if 'modification_notes' not in data_dict and 'modificationNotes' in data_dict:
            data_dict['modification_notes'] = str(data_dict['modificationNotes'])
        ret = super().to_internal_value(data_dict)
        if not ret.get('patient_id'):
            raise serializers.ValidationError({'patient_id': 'patient_id (or patientId) is required.'})
        return ret


class ClinicalAIRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalAIRecommendation
        fields = [
            'id',
            'recommendation_type',
            'recommendation',
            'confidence',
            'evidence',
            'clinician_action',
            'clinician_modified_value',
            'reviewed_at',
        ]


class ClinicalAIConsultationDetailSerializer(serializers.ModelSerializer):
    recommendations = ClinicalAIRecommendationSerializer(many=True, read_only=True)
    patient_name = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalAIConsultation
        fields = [
            'id',
            'patient',
            'patient_name',
            'status',
            'chief_complaint',
            'symptoms',
            'vitals_snapshot',
            'labs_snapshot',
            'imaging_snapshot',
            'clinical_summary',
            'model_version',
            'knowledge_version',
            'raw_response',
            'recommendations',
            'created_at',
            'completed_at',
        ]

    def get_patient_name(self, obj):
        if obj.patient:
            return f"{obj.patient.first_name} {obj.patient.last_name}"
        return ""


class ClinicalAIAuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClinicalAIAuditEvent
        fields = [
            'id',
            'user',
            'patient_ref',
            'consultation_ref',
            'event_type',
            'action_details',
            'ip_address',
            'user_agent',
            'created_at',
        ]
