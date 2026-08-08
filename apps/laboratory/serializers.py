from django.utils import timezone
from rest_framework import serializers

from .models import LabRequest, LabResult, LabTest


class LabResultParameterSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.CharField()
    unit = serializers.CharField(required=False, allow_blank=True, default='')
    range = serializers.CharField(required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=['Normal', 'Abnormal'])


class LabTestSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='test_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)

    class Meta:
        model = LabTest
        fields = [
            'id',
            'facilityId',
            'name',
            'category',
            'duration',
            'price',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def create(self, validated_data):
        facility = validated_data.pop('facility')
        test_id = validated_data.pop('test_id', None)

        if not test_id:
            existing_ids = LabTest.objects.filter(
                facility=facility,
            ).values_list('test_id', flat=True)

            max_number = 0
            for existing_id in existing_ids:
                if not isinstance(existing_id, str) or not existing_id.startswith('T'):
                    continue

                suffix = existing_id[1:]
                if suffix.isdigit():
                    max_number = max(max_number, int(suffix))

            next_number = max_number + 1
            test_id = f'T{next_number:03d}'

            while LabTest.objects.filter(facility=facility, test_id=test_id).exists():
                next_number += 1
                test_id = f'T{next_number:03d}'

        return LabTest.objects.create(
            facility=facility,
            test_id=test_id,
            **validated_data,
        )


class LabRequestSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='request_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    patientId = serializers.CharField(source='patient_id')
    testId = serializers.CharField(write_only=True)
    test = serializers.CharField(source='test.name', read_only=True)
    orderedBy_employeeId = serializers.CharField(source='ordered_by_employee_id')
    orderedBy = serializers.CharField(source='ordered_by')
    orderDate = serializers.DateField(source='order_date', required=False)
    sampleCollected = serializers.CharField(
        source='sample_collected',
        required=False,
        allow_blank=True,
        default='',
    )

    class Meta:
        model = LabRequest
        fields = [
            'id',
            'facilityId',
            'patient',
            'patientId',
            'testId',
            'test',
            'orderedBy_employeeId',
            'orderedBy',
            'orderDate',
            'sampleCollected',
            'status',
            'priority',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)

        test_external_id = attrs.pop('testId', None)
        facility = self.context.get('facility')

        if facility is None and self.instance is not None:
            facility = self.instance.facility

        if self.instance is None and not test_external_id:
            raise serializers.ValidationError({'testId': 'testId is required.'})

        if test_external_id and facility is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        if test_external_id:
            test = LabTest.objects.filter(
                facility=facility,
                test_id=test_external_id,
                is_active=True,
            ).first()
            if test is None:
                raise serializers.ValidationError({'testId': 'Lab test not found.'})
            attrs['test'] = test

        if self.instance is None and 'order_date' not in attrs:
            attrs['order_date'] = timezone.localdate()

        if self.instance is not None and 'test' in attrs:
            if attrs['test'].facility_id != self.instance.facility_id:
                raise serializers.ValidationError(
                    {'testId': 'Lab request cannot be moved to another facility.'}
                )

        return attrs

    def create(self, validated_data):
        facility = validated_data.pop('facility')
        request_id = validated_data.pop('request_id', None)

        if not request_id:
            existing_ids = LabRequest.objects.filter(
                facility=facility,
            ).values_list('request_id', flat=True)

            max_number = 0
            for existing_id in existing_ids:
                if not isinstance(existing_id, str) or not existing_id.startswith('LAB-'):
                    continue

                suffix = existing_id[4:]
                if suffix.isdigit():
                    max_number = max(max_number, int(suffix))

            next_number = max_number + 1
            request_id = f'LAB-{next_number:03d}'

            while LabRequest.objects.filter(facility=facility, request_id=request_id).exists():
                next_number += 1
                request_id = f'LAB-{next_number:03d}'

        return LabRequest.objects.create(
            facility=facility,
            request_id=request_id,
            **validated_data,
        )

    def to_representation(self, instance):
        return super().to_representation(instance)


class LabResultSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    labId = serializers.CharField(source='lab_id')
    patient = serializers.CharField(source='request.patient', read_only=True)
    test = serializers.CharField(source='request.test.name', read_only=True)
    parameters = LabResultParameterSerializer(many=True, required=False, default=list)
    completedDate = serializers.DateField(source='completed_date', required=False)
    approvedBy = serializers.CharField(
        source='approved_by',
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    class Meta:
        model = LabResult
        fields = [
            'id',
            'facilityId',
            'labId',
            'patient',
            'test',
            'parameters',
            'technician',
            'completedDate',
            'approvedBy',
            'status',
            'remarks',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'patient', 'test', 'is_active', 'created_at', 'updated_at']

    def validate_parameters(self, value):
        serializer = LabResultParameterSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return [dict(item) for item in serializer.validated_data]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        facility = self.context.get('facility')

        if facility is None and self.instance is not None:
            facility = self.instance.facility

        lab_id = attrs.get('lab_id')
        if self.instance is not None and lab_id is None:
            lab_id = self.instance.lab_id

        if facility is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        if not lab_id:
            raise serializers.ValidationError({'labId': 'labId is required.'})

        request = LabRequest.objects.filter(
            facility=facility,
            request_id=lab_id,
            is_active=True,
        ).first()
        if request is None:
            raise serializers.ValidationError({'labId': 'Lab request not found.'})

        if self.instance is not None and request.id != self.instance.request_id:
            raise serializers.ValidationError({'labId': 'Lab result cannot be reassigned.'})

        attrs['request'] = request

        if self.instance is None and 'completed_date' not in attrs:
            attrs['completed_date'] = timezone.localdate()

        if self.instance is None and not attrs.get('technician'):
            user = self.context.get('request').user
            attrs['technician'] = f"{user.first_name} {user.last_name}".strip() or user.email

        return attrs

    def create(self, validated_data):
        facility = validated_data.pop('facility')
        request = validated_data['request']
        validated_data['lab_id'] = request.request_id

        result = LabResult.objects.create(
            facility=facility,
            **validated_data,
        )

        if request.status != 'Completed':
            request.status = 'Completed'
            request.save(update_fields=['status', 'updated_at'])

        return result

    def update(self, instance, validated_data):
        result = super().update(instance, validated_data)
        request = result.request

        if result.status == 'Approved':
            request.status = 'Approved'
        elif request.status == 'Pending':
            request.status = 'Completed'
        else:
            request.status = 'Completed' if result.status == 'Awaiting Approval' else request.status

        request.save(update_fields=['status', 'updated_at'])
        return result
