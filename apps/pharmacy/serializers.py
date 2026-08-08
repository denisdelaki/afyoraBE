from rest_framework import serializers

from django.utils import timezone

from .models import Drug, Prescription


class DrugSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='drug_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    minStock = serializers.IntegerField(source='min_stock', min_value=0)
    expiryDate = serializers.DateField(source='expiry_date', required=False, allow_null=True)

    class Meta:
        model = Drug
        fields = [
            'id',
            'facilityId',
            'name',
            'category',
            'stock',
            'minStock',
            'price',
            'expiryDate',
            'manufacturer',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)

        stock = attrs.get('stock', getattr(self.instance, 'stock', 0))
        min_stock = attrs.get('min_stock', getattr(self.instance, 'min_stock', 0))

        if stock < 0:
            raise serializers.ValidationError({'stock': 'stock cannot be negative.'})

        if min_stock < 0:
            raise serializers.ValidationError({'minStock': 'minStock cannot be negative.'})

        return attrs

    def create(self, validated_data):
        facility = validated_data.pop('facility')
        drug_id = validated_data.pop('drug_id', None)

        if not drug_id:
            next_number = Drug.objects.filter(facility=facility).count() + 1
            drug_id = f'D{next_number:03d}'

            while Drug.objects.filter(facility=facility, drug_id=drug_id).exists():
                next_number += 1
                drug_id = f'D{next_number:03d}'

        return Drug.objects.create(
            facility=facility,
            drug_id=drug_id,
            **validated_data,
        )


class PrescriptionDrugItemSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True, default='')
    name = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    dosage = serializers.CharField(required=False, allow_blank=True, default='')


class PrescriptionSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='prescription_id', read_only=True)
    facilityId = serializers.IntegerField(source='facility_id', read_only=True)
    patientId = serializers.CharField(source='patient_id')
    doctorId = serializers.CharField(source='doctor_id')
    drugs = PrescriptionDrugItemSerializer(many=True, required=False, default=list)
    date = serializers.DateField(required=False)

    class Meta:
        model = Prescription
        fields = [
            'id',
            'facilityId',
            'patientId',
            'doctorId',
            'drugs',
            'status',
            'date',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'facilityId', 'is_active', 'created_at', 'updated_at']

    def validate_drugs(self, value):
        serializer = PrescriptionDrugItemSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return [dict(item) for item in serializer.validated_data]

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if self.instance is None and 'date' not in attrs:
            attrs['date'] = timezone.now().date()

        return attrs

    def create(self, validated_data):
        facility = validated_data.pop('facility')
        prescription_id = validated_data.pop('prescription_id', None)

        if not prescription_id:
            existing_ids = Prescription.objects.filter(
                facility=facility,
            ).values_list('prescription_id', flat=True)

            max_number = 0
            for existing_id in existing_ids:
                if not isinstance(existing_id, str) or not existing_id.startswith('RX'):
                    continue

                suffix = existing_id[2:]
                if suffix.isdigit():
                    max_number = max(max_number, int(suffix))

            next_number = max_number + 1
            prescription_id = f'RX{next_number:03d}'

            while Prescription.objects.filter(
                facility=facility,
                prescription_id=prescription_id,
            ).exists():
                next_number += 1
                prescription_id = f'RX{next_number:03d}'

        return Prescription.objects.create(
            facility=facility,
            prescription_id=prescription_id,
            **validated_data,
        )
