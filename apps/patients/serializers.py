from rest_framework import serializers
from django.utils import timezone
from datetime import date
import time
from django.db import IntegrityError, OperationalError, transaction

from .models import EhrRecord, Patient, PatientVisit
from pharmacy.models import Drug, Prescription


class DrugSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True, default='')
    name = serializers.CharField()
    quantity = serializers.IntegerField(min_value=0)
    dosage = serializers.CharField(required=False, allow_blank=True, default='')


class PrescriptionItemSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True, default='')
    drugs = DrugSerializer(many=True, default=list)
    status = serializers.CharField(required=False, allow_blank=True, default='Pending')
    date = serializers.DateField(required=False, allow_null=True, default=None)


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


class PatientVisitSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True)
    facilityId = serializers.IntegerField(source='facility_id')
    date = serializers.DateField(source='visit_date')
    doctor = serializers.CharField(source='served_by')
    prescription = serializers.CharField(read_only=True)
    amountBilled = serializers.DecimalField(
        source='amount_billed',
        max_digits=10,
        decimal_places=2,
        min_value=0,
    )
    whatHappened = serializers.CharField(source='what_happened', required=False, allow_blank=True)
    prescriptions = PrescriptionItemSerializer(many=True, required=False, default=list)

    class Meta:
        model = PatientVisit
        fields = [
            'id',
            'facilityId',
            'patientId',
            'date',
            'doctor',
            'diagnosis',
            'prescription',
            'prescriptions',
            'whatHappened',
            'amountBilled',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    @staticmethod
    def _parse_optional_int(value):
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip().rstrip('/')

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _resolve_facility_id_for_prescriptions(self):
        if self.instance is not None:
            return self.instance.facility_id

        raw_facility_id = self.initial_data.get('facilityId')
        if raw_facility_id is None:
            raw_facility_id = self.initial_data.get('facility_id')

        return self._parse_optional_int(raw_facility_id)

    @staticmethod
    def _resolve_drug_id(facility_id, drug_item):
        supplied_id = (drug_item.get('id') or '').strip()
        if supplied_id:
            return supplied_id

        if facility_id is None:
            return ''

        drug_name = (drug_item.get('name') or '').strip()
        if not drug_name:
            return ''

        drug = Drug.objects.filter(
            facility_id=facility_id,
            name__iexact=drug_name,
            is_active=True,
        ).first()

        return drug.drug_id if drug is not None else ''

    def validate_prescriptions(self, value):
        serializer = PrescriptionItemSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        facility_id = self._resolve_facility_id_for_prescriptions()
        result = []
        for item in serializer.validated_data:
            normalized_drugs = []
            for raw_drug in item.get('drugs', []):
                drug = dict(raw_drug)
                drug['id'] = self._resolve_drug_id(facility_id, drug)
                normalized_drugs.append(drug)

            entry = {
                'id': (item.get('id') or '').strip(),
                'drugs': normalized_drugs,
                'status': item.get('status', 'Pending'),
                'date': item['date'].isoformat() if item.get('date') is not None else None,
            }
            result.append(entry)
        return result

    def validate(self, attrs):
        attrs = super().validate(attrs)

        patient_external_id = attrs.pop('patientId', None)
        facility_id = attrs.get('facility_id')

        if self.instance is None and not patient_external_id:
            raise serializers.ValidationError({'patientId': 'patientId is required.'})

        if self.instance is not None and patient_external_id:
            if patient_external_id != self.instance.patient.patient_id:
                raise serializers.ValidationError(
                    {'patientId': 'A visit cannot be reassigned to another patient.'}
                )

        if self.instance is None and facility_id is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        target_facility_id = facility_id if facility_id is not None else self.instance.facility_id

        if patient_external_id:
            patient = Patient.objects.filter(
                patient_id=patient_external_id,
                facility_id=target_facility_id,
                is_active=True,
            ).first()
            if patient is None:
                raise serializers.ValidationError(
                    {'patientId': 'Patient not found for the provided facilityId.'}
                )
            attrs['patient'] = patient

        if self.instance is not None and 'facility_id' in attrs:
            if attrs['facility_id'] != self.instance.facility_id:
                raise serializers.ValidationError(
                    {'facilityId': 'A visit cannot be moved to another facility.'}
                )

        return attrs

    @staticmethod
    def _is_sqlite_locked_error(exc):
        return 'database is locked' in str(exc).lower()

    @staticmethod
    def _save_with_lock_retry(instance, update_fields=None, attempts=5):
        for attempt in range(attempts):
            try:
                if update_fields is None:
                    instance.save()
                else:
                    instance.save(update_fields=update_fields)
                return
            except OperationalError as exc:
                if not PatientVisitSerializer._is_sqlite_locked_error(exc):
                    raise
                if attempt == attempts - 1:
                    raise serializers.ValidationError(
                        {'detail': 'Database is busy. Please retry in a moment.'}
                    )
                time.sleep(0.05 * (attempt + 1))

    @staticmethod
    def _next_prescription_id(facility_id):
        existing_ids = Prescription.objects.filter(
            facility_id=facility_id,
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
            facility_id=facility_id,
            prescription_id=prescription_id,
        ).exists():
            next_number += 1
            prescription_id = f'RX{next_number:03d}'

        return prescription_id

    @staticmethod
    def _normalize_prescription_date(raw_date):
        if raw_date is None:
            return timezone.now().date()

        if isinstance(raw_date, date):
            return raw_date

        if isinstance(raw_date, str):
            try:
                return date.fromisoformat(raw_date)
            except ValueError:
                return timezone.now().date()

        return timezone.now().date()

    def _sync_linked_prescription(self, visit, prescriptions_payload):
        if not prescriptions_payload:
            if visit.prescription_record_id is not None or visit.prescription:
                visit.prescription_record = None
                visit.prescription = ''
                visit.prescriptions = []
                visit.save(
                    update_fields=['prescription_record', 'prescription', 'prescriptions', 'updated_at']
                )
            return

        resolved_items = []
        resolved_records = []
        seen_ids = set()

        for index, raw_item in enumerate(prescriptions_payload):
            payload = {
                'patient_id': visit.patient.patient_id,
                'doctor_id': visit.served_by,
                'drugs': raw_item.get('drugs', []),
                'status': (raw_item.get('status') or 'Pending').strip() or 'Pending',
                'date': self._normalize_prescription_date(raw_item.get('date')),
                'is_active': True,
            }

            requested_id = (raw_item.get('id') or '').strip()
            prescription = None

            if requested_id and requested_id not in seen_ids:
                prescription = Prescription.objects.filter(
                    facility_id=visit.facility_id,
                    prescription_id=requested_id,
                ).first()

            if prescription is None:
                # Retry a few times in case a concurrent request claims the same RX id.
                for attempt in range(5):
                    try:
                        with transaction.atomic():
                            prescription = Prescription.objects.create(
                                facility_id=visit.facility_id,
                                prescription_id=self._next_prescription_id(visit.facility_id),
                                **payload,
                            )
                        break
                    except IntegrityError:
                        prescription = None
                    except OperationalError as exc:
                        if not self._is_sqlite_locked_error(exc):
                            raise
                        prescription = None
                        if attempt == 4:
                            raise serializers.ValidationError(
                                {'detail': 'Database is busy. Please retry in a moment.'}
                            )
                        time.sleep(0.05 * (attempt + 1))

                if prescription is None:
                    raise serializers.ValidationError(
                        {'prescriptions': 'Unable to allocate a unique prescription ID. Please retry.'}
                    )
            else:
                for field, value in payload.items():
                    setattr(prescription, field, value)
                self._save_with_lock_retry(prescription)

            resolved_id = prescription.prescription_id
            if resolved_id in seen_ids:
                raise serializers.ValidationError(
                    {
                        'prescriptions': (
                            f'Duplicate prescription id resolved at index {index}. '
                            'Please retry the request.'
                        )
                    }
                )

            seen_ids.add(resolved_id)
            resolved_records.append(prescription)
            resolved_items.append(
                {
                    'id': resolved_id,
                    'drugs': payload['drugs'],
                    'status': payload['status'],
                    'date': payload['date'].isoformat() if payload['date'] is not None else None,
                }
            )

        primary_record = resolved_records[0]
        visit.prescription_record = primary_record
        visit.prescription = primary_record.prescription_id
        visit.prescriptions = resolved_items
        self._save_with_lock_retry(
            visit,
            update_fields=['prescription_record', 'prescription', 'prescriptions', 'updated_at'],
        )

    def create(self, validated_data):
        prescriptions_payload = validated_data.get('prescriptions', [])
        visit = super().create(validated_data)
        self._sync_linked_prescription(visit, prescriptions_payload)
        return visit

    def update(self, instance, validated_data):
        prescriptions_payload = validated_data.get('prescriptions')
        visit = super().update(instance, validated_data)

        if prescriptions_payload is not None:
            self._sync_linked_prescription(visit, prescriptions_payload)

        return visit

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id

        prescriptions = data.get('prescriptions') or []
        for prescription_item in prescriptions:
            if not isinstance(prescription_item, dict):
                continue

            drugs = prescription_item.get('drugs') or []
            for drug_item in drugs:
                if not isinstance(drug_item, dict):
                    continue
                if (drug_item.get('id') or '').strip():
                    continue
                drug_item['id'] = self._resolve_drug_id(instance.facility_id, drug_item)

        if instance.prescription_record_id:
            prescription_id = instance.prescription_record.prescription_id
            data['prescription'] = prescription_id

        return data


class EhrRecordSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    doctorNotes = serializers.CharField(source='doctor_notes', required=False, allow_blank=True)
    prescriptions = serializers.SerializerMethodField()
    labResults = serializers.SerializerMethodField()
    notes = serializers.CharField(source='doctor_notes', read_only=True)

    class Meta:
        model = EhrRecord
        fields = [
            'id',
            'facilityId',
            'patientId',
            'date',
            'doctor',
            'diagnosis',
            'symptoms',
            'treatment',
            'doctorNotes',
            'prescriptions',
            'labResults',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'date', 'prescriptions', 'labResults', 'notes', 'is_active', 'created_at', 'updated_at']

    def get_prescriptions(self, obj):
        return [item.strip() for item in (obj.treatment or '').split('\n') if item.strip()]

    def get_labResults(self, obj):
        return []

    def validate(self, attrs):
        attrs = super().validate(attrs)

        patient_external_id = attrs.pop('patientId', None)
        facility_id = attrs.get('facility_id')

        if self.instance is None and not patient_external_id:
            raise serializers.ValidationError({'patientId': 'patientId is required.'})

        if self.instance is None and facility_id is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        target_facility_id = facility_id if facility_id is not None else self.instance.facility_id

        if patient_external_id:
            patient = Patient.objects.filter(
                patient_id=patient_external_id,
                facility_id=target_facility_id,
                is_active=True,
            ).first()
            if patient is None:
                raise serializers.ValidationError(
                    {'patientId': 'Patient not found for the provided facilityId.'}
                )
            attrs['patient'] = patient

        if self.instance is not None and 'facility_id' in attrs:
            if attrs['facility_id'] != self.instance.facility_id:
                raise serializers.ValidationError(
                    {'facilityId': 'An EHR record cannot be moved to another facility.'}
                )

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        return data