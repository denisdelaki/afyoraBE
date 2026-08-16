from django.utils import timezone
from rest_framework import serializers

from .models import ImagingRequest, ImagingReport, ImagingStudy, ImagingImage


class ImagingStudySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='study_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)

    class Meta:
        model = ImagingStudy
        fields = [
            'id',
            'facilityId',
            'name',
            'category',
            'modality',
            'body_part',
            'duration',
            'price',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def create(self, validated_data):
        facility = validated_data.pop('facility', None) or self.context.get('facility')
        study_id = validated_data.pop('study_id', None)

        if not study_id:
            existing_ids = ImagingStudy.objects.filter(
                facility=facility,
            ).values_list('study_id', flat=True)

            max_number = 0
            for existing_id in existing_ids:
                if not isinstance(existing_id, str) or not existing_id.startswith('IMG'):
                    continue
                suffix = existing_id[3:]
                if suffix.isdigit():
                    max_number = max(max_number, int(suffix))

            next_number = max_number + 1
            study_id = f'IMG{next_number:03d}'

            while ImagingStudy.objects.filter(facility=facility, study_id=study_id).exists():
                next_number += 1
                study_id = f'IMG{next_number:03d}'

        return ImagingStudy.objects.create(
            facility=facility,
            study_id=study_id,
            **validated_data,
        )


class ImagingRequestSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='request_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    patientId = serializers.CharField(source='patient_id')
    studyId = serializers.CharField(write_only=True)
    studyName = serializers.CharField(source='study.name', read_only=True)
    orderedBy = serializers.CharField(source='ordered_by')
    orderDate = serializers.DateField(source='order_date', required=False)

    class Meta:
        model = ImagingRequest
        fields = [
            'id',
            'facilityId',
            'patient',
            'patientId',
            'studyId',
            'studyName',
            'orderedBy',
            'orderDate',
            'status',
            'priority',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def create(self, validated_data):
        facility = validated_data.pop('facility', None) or self.context.get('facility')
        study_id_val = validated_data.pop('studyId', None)

        # Auto-populate ordered_by_employee_id from ordered_by if not provided
        if not validated_data.get('ordered_by_employee_id'):
            validated_data['ordered_by_employee_id'] = validated_data.get('ordered_by', '')

        if study_id_val:
            try:
                study = ImagingStudy.objects.get(
                    facility=facility,
                    study_id=study_id_val,
                    is_active=True,
                )
            except ImagingStudy.DoesNotExist:
                raise serializers.ValidationError(
                    {'studyId': f"Imaging study '{study_id_val}' not found in this facility."}
                )
            validated_data['study'] = study
        else:
            raise serializers.ValidationError({'studyId': 'studyId is required.'})

        if 'order_date' not in validated_data or validated_data['order_date'] is None:
            validated_data['order_date'] = timezone.now().date()

        # Auto-generate request_id
        existing_ids = ImagingRequest.objects.filter(
            facility=facility,
        ).values_list('request_id', flat=True)

        max_number = 0
        for existing_id in existing_ids:
            if not isinstance(existing_id, str) or not existing_id.startswith('RAD'):
                continue
            suffix = existing_id[3:]
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))

        next_number = max_number + 1
        request_id = f'RAD{next_number:03d}'

        while ImagingRequest.objects.filter(facility=facility, request_id=request_id).exists():
            next_number += 1
            request_id = f'RAD{next_number:03d}'

        return ImagingRequest.objects.create(
            facility=facility,
            request_id=request_id,
            **validated_data,
        )

    def update(self, instance, validated_data):
        study_id_val = validated_data.pop('studyId', None)
        if study_id_val:
            facility = self.context['facility']
            try:
                study = ImagingStudy.objects.get(
                    facility=facility,
                    study_id=study_id_val,
                    is_active=True,
                )
            except ImagingStudy.DoesNotExist:
                raise serializers.ValidationError(
                    {'studyId': f"Imaging study '{study_id_val}' not found in this facility."}
                )
            validated_data['study'] = study

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ImagingReportSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='report_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    orderId = serializers.CharField(write_only=True, required=True)
    orderRequestId = serializers.CharField(source='request.request_id', read_only=True)
    patient = serializers.CharField(source='request.patient', read_only=True)
    patientId = serializers.CharField(source='request.patient_id', read_only=True)
    studyName = serializers.CharField(source='request.study.name', read_only=True)
    scanDate = serializers.DateField(source='scan_date', required=False)

    class Meta:
        model = ImagingReport
        fields = [
            'id',
            'facilityId',
            'orderId',
            'orderRequestId',
            'patient',
            'patientId',
            'studyName',
            'radiologist',
            'scanDate',
            'findings',
            'impression',
            'recommendations',
            'status',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'facilityId', 'orderRequestId', 'patient', 'patientId',
            'studyName', 'is_active', 'created_at', 'updated_at',
        ]

    def create(self, validated_data):
        facility = validated_data.pop('facility', None) or self.context.get('facility')
        order_id_val = validated_data.pop('orderId', None)

        if not order_id_val:
            raise serializers.ValidationError({'orderId': 'orderId is required.'})

        try:
            imaging_request = ImagingRequest.objects.get(
                facility=facility,
                request_id=order_id_val,
                is_active=True,
            )
        except ImagingRequest.DoesNotExist:
            raise serializers.ValidationError(
                {'orderId': f"Imaging request '{order_id_val}' not found in this facility."}
            )

        # Check if report already exists
        if hasattr(imaging_request, 'report') and imaging_request.report.is_active:
            raise serializers.ValidationError(
                {'orderId': f"A report already exists for order '{order_id_val}'."}
            )

        if 'scan_date' not in validated_data or validated_data['scan_date'] is None:
            validated_data['scan_date'] = imaging_request.order_date

        # Auto-generate report_id
        existing_ids = ImagingReport.objects.filter(
            facility=facility,
        ).values_list('report_id', flat=True)

        max_number = 0
        for existing_id in existing_ids:
            if not isinstance(existing_id, str) or not existing_id.startswith('RPT'):
                continue
            suffix = existing_id[3:]
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))

        next_number = max_number + 1
        report_id = f'RPT{next_number:03d}'

        while ImagingReport.objects.filter(facility=facility, report_id=report_id).exists():
            next_number += 1
            report_id = f'RPT{next_number:03d}'

        report = ImagingReport.objects.create(
            facility=facility,
            report_id=report_id,
            request=imaging_request,
            **validated_data,
        )

        # Update request status to Completed/Approved
        imaging_request.status = 'Completed'
        imaging_request.save(update_fields=['status', 'updated_at'])

        return report

    def update(self, instance, validated_data):
        validated_data.pop('orderId', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ImagingImageSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    orderId = serializers.CharField(write_only=True, required=False)
    orderRequestId = serializers.CharField(source='request.request_id', read_only=True)
    uploadedAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = ImagingImage
        fields = [
            'id',
            'facilityId',
            'orderId',
            'orderRequestId',
            'name',
            'url',
            'source',
            'uploadedAt',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'orderRequestId', 'uploadedAt', 'created_at', 'updated_at']

    def create(self, validated_data):
        facility = validated_data.pop('facility', None) or self.context.get('facility')
        order_id_val = validated_data.pop('orderId', None)

        if not order_id_val:
            raise serializers.ValidationError({'orderId': 'orderId is required.'})

        try:
            imaging_request = ImagingRequest.objects.get(
                facility=facility,
                request_id=order_id_val,
                is_active=True,
            )
        except ImagingRequest.DoesNotExist:
            raise serializers.ValidationError(
                {'orderId': f"Imaging request '{order_id_val}' not found in this facility."}
            )

        return ImagingImage.objects.create(
            facility=facility,
            request=imaging_request,
            **validated_data,
        )

