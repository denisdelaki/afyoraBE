from rest_framework import serializers
from .models import InsuranceProvider, DHAClaim, DHAAuthorization, DHAPrescription, DHAEmergencyClaim, DHALog


class InsuranceProviderSerializer(serializers.ModelSerializer):
    api_token_masked = serializers.SerializerMethodField()

    class Meta:
        model = InsuranceProvider
        fields = [
            'id', 'facility_id', 'name', 'code', 'payer_type', 'gateway_url',
            'facility_code', 'api_token', 'api_token_masked', 'environment',
            'is_active', 'sandbox_mode', 'supported_schemes',
            'last_ping_status', 'last_ping_at', 'created_at', 'updated_at'
        ]
        extra_kwargs = {
            'api_token': {'write_only': True, 'required': False}
        }

    def get_api_token_masked(self, obj):
        if obj.api_token:
            return f"***MASKED-{obj.api_token[-4:]}***" if len(obj.api_token) > 4 else "***MASKED***"
        return "Not Configured"


class DHAClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = DHAClaim
        fields = '__all__'


class DHAAuthorizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DHAAuthorization
        fields = '__all__'


class DHAPrescriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DHAPrescription
        fields = '__all__'


class DHAEmergencyClaimSerializer(serializers.ModelSerializer):
    class Meta:
        model = DHAEmergencyClaim
        fields = '__all__'


class DHALogSerializer(serializers.ModelSerializer):
    class Meta:
        model = DHALog
        fields = '__all__'


# ------------------------------------------------------------------
# REQUEST PAYLOAD INPUT SERIALIZERS
# ------------------------------------------------------------------
class EligibilityQuerySerializer(serializers.Serializer):
    identification_number = serializers.CharField(required=True)
    identification_type = serializers.CharField(required=True)


class AuthorizeRequestSerializer(serializers.Serializer):
    patient_id = serializers.CharField(required=True)
    service_type = serializers.ChoiceField(choices=['OUTPATIENT', 'INPATIENT'], required=True)
    otp = serializers.CharField(required=True)
    interventions = serializers.ListField(child=serializers.CharField(), required=True)
    patient_name = serializers.CharField(required=False, allow_blank=True)


class VisitRequestSerializer(serializers.Serializer):
    patient_id = serializers.CharField(required=True)
    service_type = serializers.ChoiceField(choices=['CAPITATION', 'OUTPATIENT', 'INPATIENT', 'EMERGENCY'], required=True)
    otp = serializers.CharField(required=True)
    intervention_codes = serializers.ListField(child=serializers.CharField(), required=True)


class ClaimAttachmentSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    intervention_code = serializers.CharField(required=True)
    document_type = serializers.CharField(required=True)
    file_blob = serializers.FileField(required=False)


class ClaimDiagnosisSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    icd_code = serializers.CharField(required=True)
    intervention_code = serializers.CharField(required=True)
    facilityID = serializers.CharField(required=False, allow_blank=True)
    facilityIDType = serializers.CharField(required=False, allow_blank=True)


class ClaimLineItemSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    intervention_code = serializers.CharField(required=True)
    unit_price = serializers.FloatField(required=True)
    quantity = serializers.IntegerField(required=True)
    scheme_code = serializers.CharField(required=False, allow_blank=True)
    charge_date = serializers.CharField(required=False, allow_blank=True)


class PrescriptionCreateSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    intervention_code = serializers.CharField(required=True)
    items = serializers.ListField(child=serializers.DictField(), required=True)
    identification_number = serializers.CharField(required=False, allow_blank=True)
    identification_type = serializers.CharField(required=False, allow_blank=True)
    regulation_body = serializers.CharField(required=False, allow_blank=True)


class DispenseCreateSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    intervention_code = serializers.CharField(required=True)
    actual_products = serializers.ListField(child=serializers.DictField(), required=True)
    doctors = serializers.ListField(child=serializers.DictField(), required=True)


class DischargeRequestSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    discharge_date = serializers.CharField(required=True)
    discharge_reason = serializers.ChoiceField(choices=['RECOVERED', 'REFERRED', 'DECEASED', 'ABSCONDED', 'OTHER'], required=True)
    invoice_number = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)


class CloseClaimSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    cancel_reason_text = serializers.CharField(required=True)
    cancel_reason_type = serializers.ChoiceField(
        choices=['WRONG_PATIENT', 'NO_SERVICE_GIVEN', 'WRONG_BENEFIT', 'EXPIRED_VISIT', 'EXHAUSTED_BENEFIT', 'OTHER'],
        required=True
    )


class EmergencyCaseSerializer(serializers.Serializer):
    brought_by = serializers.ChoiceField(choices=['RELATIVE', 'UNKNOWN', 'SAMARITAN', 'PARAMEDICS'], required=True)
    identification_number = serializers.CharField(required=True)
    identification_type = serializers.CharField(required=True)
    interventions = serializers.ListField(child=serializers.CharField(), required=True)
    mode_of_arrival = serializers.ChoiceField(choices=['AMBULANCE', 'WALK-IN', 'OTHER'], required=True)
    reference_number = serializers.CharField(required=True)
    regulation_body = serializers.CharField(required=True)
    beneficiary_cr_id = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    otp = serializers.CharField(required=False, allow_blank=True)


class EMTClaimSerializer(serializers.Serializer):
    consent_token = serializers.CharField(required=True)
    protocol_code = serializers.CharField(required=True)
    case_number = serializers.CharField(required=True)
    practitioner_reg_number = serializers.CharField(required=True)
    beneficiary_cr_id = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)
    provider_registration_number = serializers.CharField(required=True)
    diagnoses = serializers.CharField(required=True)
    interventions = serializers.CharField(required=True)
