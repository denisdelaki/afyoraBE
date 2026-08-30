# billing/serializers.py
from rest_framework import serializers
from core.models import Facility
from patients.models import Patient
from .models import Invoice, InvoiceItem, InsuranceInfo, Payment


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['service', 'amount']


class InsuranceInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceInfo
        fields = ['company', 'coverage', 'claim']


class InvoiceSerializer(serializers.ModelSerializer):
    patient = serializers.SerializerMethodField()
    patientId = serializers.SerializerMethodField()
    facilityId = serializers.SerializerMethodField()
    items = InvoiceItemSerializer(many=True)
    insurance = InsuranceInfoSerializer(required=False, allow_null=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    tax = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    paymentMethod = serializers.CharField(source='payment_method', allow_null=True, required=False)

    class Meta:
        model = Invoice
        fields = [
            'id', 'patient', 'patientId', 'facilityId', 'date', 'items',
            'subtotal', 'tax', 'total', 'status', 'paymentMethod', 'insurance',
        ]
        read_only_fields = ['id', 'date', 'status']

    def get_patient(self, obj):
        if obj.patient:
            full_name = f"{obj.patient.first_name} {obj.patient.last_name}".strip()
            return full_name or obj.patient.patient_id
        return ""

    def get_patientId(self, obj):
        if obj.patient:
            return obj.patient.patient_id or str(obj.patient.id)
        return ""

    def get_facilityId(self, obj):
        return obj.facility_id if obj.facility_id else None

    def _resolve_patient(self, patient_val, facility_id=None):
        if not patient_val:
            raise serializers.ValidationError({'patientId': 'patientId is required.'})

        patient = None

        # 1. Try string patient_id (e.g. PAT0001) first if it's string
        if isinstance(patient_val, str):
            clean_str = patient_val.strip()
            qs = Patient.objects.filter(patient_id__iexact=clean_str)
            if facility_id:
                qs = qs.filter(facility_id=facility_id)
            patient = qs.first()

        # 2. Try integer ID if patient is digit or integer
        if not patient and (isinstance(patient_val, int) or (isinstance(patient_val, str) and patient_val.isdigit())):
            qs = Patient.objects.filter(id=int(patient_val))
            if facility_id:
                qs = qs.filter(facility_id=facility_id)
            patient = qs.first()

        # 3. Fallback: try patient_id without facility filter
        if not patient and isinstance(patient_val, str):
            patient = Patient.objects.filter(patient_id__iexact=patient_val.strip()).first()

        if not patient:
            raise serializers.ValidationError(
                {'patientId': f"Patient '{patient_val}' not found."}
            )

        return patient

    def create(self, validated_data):
        request = self.context.get('request')
        raw_data = request.data if request else {}

        facility_val = (
            raw_data.get('facilityId')
            or raw_data.get('facility_id')
            or (request.query_params.get('facilityId') if request else None)
            or (request.query_params.get('facility_id') if request else None)
        )
        facility_id = None
        if facility_val is not None:
            clean_fac = str(facility_val).strip().rstrip('/')
            if clean_fac.isdigit():
                facility_id = int(clean_fac)

        if not facility_id and request and getattr(request.user, 'facility_id', None):
            facility_id = request.user.facility_id

        patient_val = (
            raw_data.get('patientId')
            or raw_data.get('patient_id')
            or raw_data.get('patient')
        )
        patient = self._resolve_patient(patient_val, facility_id=facility_id)

        items_data = validated_data.pop('items', [])
        insurance_data = validated_data.pop('insurance', None)

        # Auto-merge charges based on include flags
        from .utils import (
            get_patient_pharmacy_charges,
            get_patient_lab_charges,
            get_patient_radiology_charges,
        )
        existing_services = {item.get('service') for item in items_data if isinstance(item, dict)}

        def _merge_charges(charge_items):
            for c_item in charge_items:
                if c_item['service'] not in existing_services:
                    items_data.append({'service': c_item['service'], 'amount': c_item['amount']})
                    existing_services.add(c_item['service'])

        if raw_data.get('includePharmacy') or raw_data.get('include_pharmacy'):
            _, pharmacy_items = get_patient_pharmacy_charges(patient, facility_id=facility_id)
            _merge_charges(pharmacy_items)

        if raw_data.get('includeLabCharges') or raw_data.get('include_lab_charges'):
            _, lab_items = get_patient_lab_charges(patient, facility_id=facility_id)
            _merge_charges(lab_items)

        if raw_data.get('includeRadiologyCharges') or raw_data.get('include_radiology_charges'):
            _, radiology_items = get_patient_radiology_charges(patient, facility_id=facility_id)
            _merge_charges(radiology_items)

        invoice = Invoice.objects.create(
            facility_id=facility_id,
            patient=patient,
            **validated_data
        )

        for item in items_data:
            InvoiceItem.objects.create(invoice=invoice, **item)

        if insurance_data:
            InsuranceInfo.objects.create(invoice=invoice, **insurance_data)

        return invoice

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        insurance_data = validated_data.pop('insurance', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                InvoiceItem.objects.create(invoice=instance, **item)

        if insurance_data is not None:
            InsuranceInfo.objects.update_or_create(invoice=instance, defaults=insurance_data)

        return instance


class PaymentSerializer(serializers.ModelSerializer):
    invoice = serializers.CharField(source='invoice.id', read_only=True)
    patient = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'patient', 'amount', 'method', 'date', 'status']

    def get_patient(self, obj):
        if obj.invoice and obj.invoice.patient:
            patient = obj.invoice.patient
            full_name = f"{patient.first_name} {patient.last_name}".strip()
            return full_name or patient.patient_id
        return ""


class RecordPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    method = serializers.CharField(max_length=50)


class MpesaConfigSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility.id', read_only=True)

    class Meta:
        from .models import MpesaConfig
        model = MpesaConfig
        fields = [
            'id', 'facilityId', 'shortcode', 'passkey', 'consumer_key',
            'consumer_secret', 'environment', 'transaction_type',
            'account_reference_prefix', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'facilityId', 'created_at', 'updated_at']
        extra_kwargs = {
            'passkey': {'write_only': False},
            'consumer_secret': {'write_only': False},
        }


class MpesaSTKPushRequestSerializer(serializers.Serializer):
    invoiceId = serializers.CharField(max_length=50)
    phoneNumber = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


class MpesaTransactionSerializer(serializers.ModelSerializer):
    invoiceId = serializers.CharField(source='invoice.id', read_only=True)

    class Meta:
        from .models import MpesaTransaction
        model = MpesaTransaction
        fields = [
            'id', 'invoiceId', 'phone_number', 'amount', 'checkout_request_id',
            'merchant_request_id', 'status', 'result_code', 'result_desc',
            'mpesa_receipt_number', 'transaction_date', 'created_at'
        ]