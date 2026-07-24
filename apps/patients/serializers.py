from rest_framework import serializers
from django.utils import timezone

from .models import Patient


class PatientSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='patient_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id')
    firstName = serializers.CharField(source='first_name')
    lastName = serializers.CharField(source='last_name')
    age = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    dateOfBirth = serializers.DateField(source='date_of_birth', required=False, allow_null=True)
    maritalStatus = serializers.CharField(source='marital_status', required=False, allow_blank=True)
    bloodGroup = serializers.CharField(source='blood_group', required=False, allow_blank=True)
    emergencyContactName = serializers.CharField(
        source='emergency_contact_name',
        required=False,
        allow_blank=True,
    )
    emergencyContactPhone = serializers.CharField(
        source='emergency_contact_phone',
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Patient
        fields = [
            'id',
            'facilityId',
            'firstName',
            'lastName',
            'gender',
            'age',
            'dateOfBirth',
            'phone',
            'email',
            'address',
            'city',
            'maritalStatus',
            'bloodGroup',
            'emergencyContactName',
            'emergencyContactPhone',
            'allergies',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)

        provided_age = attrs.get('age')
        provided_dob = attrs.get('date_of_birth')

        if provided_age is not None and provided_dob is not None:
            today = timezone.now().date()
            computed_age = (
                today.year
                - provided_dob.year
                - ((today.month, today.day) < (provided_dob.month, provided_dob.day))
            )
            if abs(provided_age - computed_age) > 1:
                raise serializers.ValidationError(
                    {'age': 'Provided age does not match dateOfBirth.'}
                )

        if self.instance is not None and 'facility_id' in attrs:
            if attrs['facility_id'] != self.instance.facility_id:
                raise serializers.ValidationError(
                    {'facilityId': 'A patient cannot be moved to another facility.'}
                )

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.date_of_birth is not None:
            today = timezone.now().date()
            data['age'] = (
                today.year
                - instance.date_of_birth.year
                - ((today.month, today.day) < (instance.date_of_birth.month, instance.date_of_birth.day))
            )

        return data

    def create(self, validated_data):
        facility_id = validated_data.pop('facility_id')
        patient_id = validated_data.pop('patient_id', None)

        if not patient_id:
            next_number = Patient.objects.filter(facility_id=facility_id).count() + 1
            patient_id = f'PAT{next_number:04d}'
            while Patient.objects.filter(
                facility_id=facility_id,
                patient_id=patient_id,
            ).exists():
                next_number += 1
                patient_id = f'PAT{next_number:04d}'

        return Patient.objects.create(
            facility_id=facility_id,
            patient_id=patient_id,
            **validated_data,
        )