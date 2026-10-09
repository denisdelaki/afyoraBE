from rest_framework import serializers
from django.utils import timezone
from datetime import date
import time
from django.db import IntegrityError, OperationalError, transaction

from .models import (
    AllergyItem,
    CpoeOrder,
    EhrRecord,
    OutpatientTicket,
    OutpatientTicketMovement,
    Patient,
    PatientVisit,
    PatientVital,
    ProblemItem,
)
from pharmacy.models import Drug, Prescription
from core.models import User

VALID_CLINICAL_CODE_SYSTEMS = {
    'KNHTS',
    'ICD-10-WHO',
    'ICD-10',
    'ICD10',
    'SNOMED-CT',
    'SNOMED CT',
    'SNOMED',
    'LOINC',
    'http://snomed.info/sct',
    'http://hl7.org/fhir/sid/icd-10',
    'http://id.who.int/icd/release/10',
    'http://loinc.org',
    'http://knhts.health.go.ke',
}


def is_valid_clinical_code_system(system):
    if not system:
        return False
    sys_str = system.strip()
    if sys_str in VALID_CLINICAL_CODE_SYSTEMS or sys_str.upper() in VALID_CLINICAL_CODE_SYSTEMS:
        return True
    lower = sys_str.lower()
    if 'snomed' in lower or 'icd-10' in lower or 'icd10' in lower or 'loinc' in lower or 'knhts' in lower:
        return True
    return False


def validate_clinical_concept(diagnosis, diagnosis_code=None, diagnosis_system=None, diagnosis_text=None):
    """
    Validate and normalise clinical terminology fields on a clinical record.

    DHA Compliance (DHA_COMPLIANCE_MODE=True, which is the default):
      - When `diagnosis` is provided, `diagnosisCode` is REQUIRED.
      - `diagnosisSystem` must be one of the DHA-approved code systems.
      - `diagnosisText` defaults to the diagnosis string when omitted.

    Raises serializers.ValidationError (HTTP 400) on any violation.
    Returns a normalised dict ready to be persisted on the model.
    """
    from django.conf import settings as django_settings

    diagnosis = (diagnosis or '').strip()
    code = (diagnosis_code or '').strip()
    system = (diagnosis_system or 'KNHTS').strip() or 'KNHTS'
    text = (diagnosis_text or diagnosis or '').strip()

    dha_strict = getattr(django_settings, 'DHA_COMPLIANCE_MODE', True)

    # --- Symmetric presence checks ---
    if diagnosis and not code:
        if dha_strict:
            raise serializers.ValidationError({
                'diagnosisCode': (
                    'diagnosisCode is required when diagnosis is provided. '
                    'Select a coded clinical concept via the KNHTS search '
                    '(DHA Compliance Mode is enabled).'
                )
            })
        # In non-strict mode we allow free-text but warn
        # (handled by the frontend indicator)

    if code and not diagnosis:
        raise serializers.ValidationError(
            {'diagnosis': 'diagnosis is required when diagnosisCode is provided.'}
        )

    if code and not system:
        raise serializers.ValidationError(
            {'diagnosisSystem': 'diagnosisSystem is required when diagnosisCode is provided.'}
        )

    if system and not is_valid_clinical_code_system(system):
        raise serializers.ValidationError({
            'diagnosisSystem': (
                f'Unsupported clinical code system "{system}". '
                f'DHA-approved systems: ICD-10-WHO, KNHTS, LOINC, SNOMED-CT.'
            )
        })

    if diagnosis and not text:
        raise serializers.ValidationError(
            {'diagnosisText': 'diagnosisText cannot be empty when diagnosis is provided.'}
        )

    return {
        'diagnosis': diagnosis,
        'diagnosis_code': code,
        'diagnosis_system': system,
        'diagnosis_text': text,
    }



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
    nationalId = serializers.CharField(
        source='national_id_or_birth_certificate',
        required=False,
        allow_blank=True,
        allow_null=True,
        default='',
    )
    firstName = serializers.CharField(source='first_name')
    lastName = serializers.CharField(source='last_name')
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default='',
    )
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
            'nationalId',
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
    diagnosisCode = serializers.CharField(source='diagnosis_code', required=False, allow_blank=True, default='')
    diagnosisSystem = serializers.CharField(source='diagnosis_system', required=False, allow_blank=True, default='KNHTS')
    diagnosisText = serializers.CharField(source='diagnosis_text', required=False, allow_blank=True, default='')
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
            'diagnosisCode',
            'diagnosisSystem',
            'diagnosisText',
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

        normalized_concept = validate_clinical_concept(
            attrs.get('diagnosis'),
            attrs.get('diagnosis_code'),
            attrs.get('diagnosis_system'),
            attrs.get('diagnosis_text'),
        )
        attrs['diagnosis'] = normalized_concept['diagnosis']
        attrs['diagnosis_code'] = normalized_concept['diagnosis_code']
        attrs['diagnosis_system'] = normalized_concept['diagnosis_system']
        attrs['diagnosis_text'] = normalized_concept['diagnosis_text']
        attrs['diagnosis_lookup_timestamp'] = timezone.now()

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

        vitals_payload = self.initial_data.get('vitals')
        if vitals_payload and isinstance(vitals_payload, dict):
            vital_serializer = PatientVitalSerializer(data=vitals_payload)
            if vital_serializer.is_valid():
                request = self.context.get('request')
                user = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None
                captured_by_name = (
                    vitals_payload.get('capturedByName')
                    or vitals_payload.get('captured_by_name')
                    or (user.get_full_name() if user else '')
                    or (user.username if user else '')
                )
                vital_serializer.save(
                    facility_id=visit.facility_id,
                    patient=visit.patient,
                    visit=visit,
                    captured_by=user,
                    captured_by_name=captured_by_name,
                )

        return visit

    def update(self, instance, validated_data):
        prescriptions_payload = validated_data.get('prescriptions')
        visit = super().update(instance, validated_data)

        if prescriptions_payload is not None:
            self._sync_linked_prescription(visit, prescriptions_payload)

        vitals_payload = self.initial_data.get('vitals')
        if vitals_payload and isinstance(vitals_payload, dict):
            existing_vital = instance.vitals.filter(is_active=True).first()
            vital_serializer = PatientVitalSerializer(
                instance=existing_vital,
                data=vitals_payload,
                partial=True,
            )
            if vital_serializer.is_valid():
                request = self.context.get('request')
                user = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None
                captured_by_name = (
                    vitals_payload.get('capturedByName')
                    or vitals_payload.get('captured_by_name')
                    or (user.get_full_name() if user else '')
                    or (user.username if user else '')
                )
                vital_serializer.save(
                    facility_id=visit.facility_id,
                    patient=visit.patient,
                    visit=visit,
                    captured_by=user if user else (existing_vital.captured_by if existing_vital else None),
                    captured_by_name=captured_by_name or (existing_vital.captured_by_name if existing_vital else ''),
                )

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

        linked_vital = instance.vitals.filter(is_active=True).first()
        if linked_vital:
            data['vitals'] = PatientVitalSerializer(linked_vital).data
        else:
            data['vitals'] = None

        return data


class OutpatientTicketMovementSerializer(serializers.ModelSerializer):
    fromDestination = serializers.CharField(source='from_destination')
    toDestination = serializers.CharField(source='to_destination')
    forwardedBy = serializers.IntegerField(source='forwarded_by_id', read_only=True)
    assignedTo = serializers.IntegerField(source='assigned_to_id', read_only=True)

    class Meta:
        model = OutpatientTicketMovement
        fields = [
            'id', 'fromDestination', 'toDestination', 'forwardedBy', 'assignedTo',
            'notes', 'created_at',
        ]


class OutpatientTicketSerializer(serializers.ModelSerializer):
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    patientId = serializers.CharField(write_only=True, required=False)
    patientName = serializers.SerializerMethodField()
    ticketNumber = serializers.CharField(source='ticket_number', read_only=True)
    assignedTo = serializers.PrimaryKeyRelatedField(
        source='assigned_to', queryset=User.objects.all(),
        required=False, allow_null=True,
    )
    createdBy = serializers.IntegerField(source='created_by_id', read_only=True)
    calledBy = serializers.IntegerField(source='called_by_id', read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', read_only=True)
    movements = OutpatientTicketMovementSerializer(many=True, read_only=True)

    class Meta:
        model = OutpatientTicket
        fields = [
            'id', 'facilityId', 'patientId', 'patientName', 'ticketNumber', 'destination',
            'assignedTo', 'status', 'createdBy', 'calledBy', 'notes', 'completedAt',
            'movements', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'ticketNumber', 'status', 'createdBy', 'calledBy', 'completedAt',
            'movements', 'created_at', 'updated_at',
        ]

    def get_patientName(self, obj):
        return f'{obj.patient.first_name} {obj.patient.last_name}'.strip()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        patient_id = attrs.pop('patientId', None)
        facility_id = attrs.get('facility_id')

        if self.instance is None:
            if not patient_id:
                raise serializers.ValidationError({'patientId': 'patientId is required.'})
            if facility_id is None:
                raise serializers.ValidationError({'facilityId': 'facilityId is required.'})
            patient = Patient.objects.filter(
                facility_id=facility_id, patient_id=patient_id, is_active=True,
            ).first()
            if patient is None:
                raise serializers.ValidationError({'patientId': 'Patient not found for the provided facilityId.'})
            attrs['patient'] = patient
        elif 'facility_id' in attrs and attrs['facility_id'] != self.instance.facility_id:
            raise serializers.ValidationError({'facilityId': 'A ticket cannot be moved to another facility.'})

        assigned_to = attrs.get('assigned_to')
        target_facility_id = facility_id or (self.instance.facility_id if self.instance else None)
        if assigned_to is not None and assigned_to.facility_id != target_facility_id:
            raise serializers.ValidationError({'assignedTo': 'The assigned user must belong to this facility.'})
        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['patientId'] = instance.patient.patient_id
        return ret


class EhrRecordSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    diagnosisCode = serializers.CharField(source='diagnosis_code', required=False, allow_blank=True, default='')
    diagnosisSystem = serializers.CharField(source='diagnosis_system', required=False, allow_blank=True, default='KNHTS')
    diagnosisText = serializers.CharField(source='diagnosis_text', required=False, allow_blank=True, default='')
    doctorNotes = serializers.CharField(source='doctor_notes', required=False, allow_blank=True)
    prescriptions = serializers.SerializerMethodField()
    labResults = serializers.SerializerMethodField()
    vitals = serializers.SerializerMethodField()
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
            'diagnosisCode',
            'diagnosisSystem',
            'diagnosisText',
            'symptoms',
            'treatment',
            'doctorNotes',
            'prescriptions',
            'labResults',
            'vitals',
            'notes',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'date', 'prescriptions', 'labResults', 'vitals', 'notes', 'is_active', 'created_at', 'updated_at']

    def get_prescriptions(self, obj):
        return [item.strip() for item in (obj.treatment or '').split('\n') if item.strip()]

    def get_labResults(self, obj):
        return []

    def get_vitals(self, obj):
        vital = PatientVital.objects.filter(
            facility_id=obj.facility_id,
            patient=obj.patient,
            is_active=True,
        ).first()
        return PatientVitalSerializer(vital).data if vital else None

    def create(self, validated_data):
        ehr = super().create(validated_data)
        vitals_payload = self.initial_data.get('vitals')
        if vitals_payload and isinstance(vitals_payload, dict):
            vital_serializer = PatientVitalSerializer(data=vitals_payload)
            if vital_serializer.is_valid():
                request = self.context.get('request')
                user = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None
                captured_by_name = (
                    vitals_payload.get('capturedByName')
                    or vitals_payload.get('captured_by_name')
                    or (user.get_full_name() if user else '')
                    or (user.username if user else '')
                )
                vital_serializer.save(
                    facility_id=ehr.facility_id,
                    patient=ehr.patient,
                    captured_by=user,
                    captured_by_name=captured_by_name,
                )
        return ehr

    def update(self, instance, validated_data):
        ehr = super().update(instance, validated_data)
        vitals_payload = self.initial_data.get('vitals')
        if vitals_payload and isinstance(vitals_payload, dict):
            existing_vital = PatientVital.objects.filter(
                facility_id=ehr.facility_id,
                patient=ehr.patient,
                is_active=True,
            ).first()
            vital_serializer = PatientVitalSerializer(
                instance=existing_vital,
                data=vitals_payload,
                partial=True,
            )
            if vital_serializer.is_valid():
                request = self.context.get('request')
                user = request.user if request and hasattr(request, 'user') and request.user.is_authenticated else None
                captured_by_name = (
                    vitals_payload.get('capturedByName')
                    or vitals_payload.get('captured_by_name')
                    or (user.get_full_name() if user else '')
                    or (user.username if user else '')
                )
                vital_serializer.save(
                    facility_id=ehr.facility_id,
                    patient=ehr.patient,
                    captured_by=user if user else (existing_vital.captured_by if existing_vital else None),
                    captured_by_name=captured_by_name or (existing_vital.captured_by_name if existing_vital else ''),
                )
        return ehr

    def validate(self, attrs):
        attrs = super().validate(attrs)

        patient_external_id = attrs.pop('patientId', None)
        facility_id = attrs.get('facility_id')

        normalized_concept = validate_clinical_concept(
            attrs.get('diagnosis'),
            attrs.get('diagnosis_code'),
            attrs.get('diagnosis_system'),
            attrs.get('diagnosis_text'),
        )
        attrs['diagnosis'] = normalized_concept['diagnosis']
        attrs['diagnosis_code'] = normalized_concept['diagnosis_code']
        attrs['diagnosis_system'] = normalized_concept['diagnosis_system']
        attrs['diagnosis_text'] = normalized_concept['diagnosis_text']
        attrs['diagnosis_lookup_timestamp'] = timezone.now()

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


from django.db import models


def _resolve_patient_for_write(attrs, instance, target_model_label):
    """Shared patientId/facilityId → Patient FK resolution for EHR & Vitals records."""
    patient_ref = attrs.pop('patientId', None) or attrs.pop('patient_id', None)
    if patient_ref is None and 'patient' in attrs:
        patient_val = attrs.pop('patient')
        if isinstance(patient_val, Patient):
            patient_ref = patient_val.patient_id
        else:
            patient_ref = patient_val

    facility_id = attrs.get('facility_id')

    if instance is None and not patient_ref:
        raise serializers.ValidationError({'patientId': 'patientId is required.'})
    if instance is None and facility_id is None:
        raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

    target_facility_id = facility_id if facility_id is not None else instance.facility_id

    if patient_ref:
        if isinstance(patient_ref, Patient):
            patient = patient_ref
        else:
            patient_str = str(patient_ref).strip()
            query = Patient.objects.filter(facility_id=target_facility_id, is_active=True)
            if patient_str.isdigit():
                patient = query.filter(models.Q(patient_id=patient_str) | models.Q(id=int(patient_str))).first()
            else:
                patient = query.filter(patient_id=patient_str).first()

        if patient is None:
            raise serializers.ValidationError(
                {'patientId': f'Patient "{patient_ref}" not found for the provided facilityId.'}
            )
        if patient.facility_id != target_facility_id:
            raise serializers.ValidationError(
                {'patientId': f'Patient does not belong to facility {target_facility_id}.'}
            )
        attrs['patient'] = patient

    if instance is not None and 'facility_id' in attrs and attrs['facility_id'] != instance.facility_id:
        raise serializers.ValidationError(
            {'facilityId': f'A {target_model_label} cannot be moved to another facility.'}
        )

    return attrs



class ProblemItemSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    onsetDate = serializers.DateField(source='onset_date', required=False, allow_null=True)
    resolvedDate = serializers.DateField(source='resolved_date', required=False, allow_null=True)
    recordedBy = serializers.CharField(source='recorded_by', required=False, allow_blank=True)

    class Meta:
        model = ProblemItem
        fields = [
            'id', 'facilityId', 'patientId', 'code', 'system', 'display',
            'status', 'onsetDate', 'resolvedDate', 'notes', 'recordedBy',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return _resolve_patient_for_write(attrs, self.instance, 'problem item')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        return data


class AllergyItemSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    allergenName = serializers.CharField(source='allergen_name')
    allergenCode = serializers.CharField(source='allergen_code', required=False, allow_blank=True)
    allergyType = serializers.CharField(source='allergy_type', required=False)
    onsetDate = serializers.DateField(source='onset_date', required=False, allow_null=True)

    class Meta:
        model = AllergyItem
        fields = [
            'id', 'facilityId', 'patientId', 'allergenName', 'allergenCode',
            'allergyType', 'severity', 'reaction', 'onsetDate',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return _resolve_patient_for_write(attrs, self.instance, 'allergy item')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        return data


class CpoeOrderSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    orderType = serializers.CharField(source='order_type')
    orderedBy = serializers.CharField(source='ordered_by', required=False, allow_blank=True)
    orderDate = serializers.DateField(source='order_date', read_only=True)
    billingAmount = serializers.DecimalField(source='billing_amount', max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = CpoeOrder
        fields = [
            'id', 'facilityId', 'patientId', 'orderType', 'title', 'code', 'system',
            'instructions', 'orderedBy', 'orderDate', 'status', 'billingAmount',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'orderDate', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return _resolve_patient_for_write(attrs, self.instance, 'CPOE order')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        return data


class PatientVitalSerializer(serializers.ModelSerializer):
    patientId = serializers.CharField(write_only=True, required=False)
    facilityId = serializers.IntegerField(source='facility_id', required=False)
    visitId = serializers.IntegerField(source='visit_id', required=False, allow_null=True)
    ticketId = serializers.IntegerField(source='ticket_id', required=False, allow_null=True)
    capturedById = serializers.IntegerField(source='captured_by_id', required=False, allow_null=True)
    capturedByName = serializers.CharField(source='captured_by_name', required=False, allow_blank=True)

    temperatureC = serializers.DecimalField(source='temperature_c', max_digits=4, decimal_places=1, required=False, allow_null=True)
    systolicBp = serializers.IntegerField(source='systolic_bp', required=False, allow_null=True)
    diastolicBp = serializers.IntegerField(source='diastolic_bp', required=False, allow_null=True)
    heartRateBpm = serializers.IntegerField(source='heart_rate_bpm', required=False, allow_null=True)
    respiratoryRate = serializers.IntegerField(source='respiratory_rate', required=False, allow_null=True)
    spo2Percent = serializers.IntegerField(source='spo2_percent', required=False, allow_null=True)
    bloodGlucoseMmol = serializers.DecimalField(source='blood_glucose_mmol', max_digits=5, decimal_places=2, required=False, allow_null=True)
    heightCm = serializers.DecimalField(source='height_cm', max_digits=5, decimal_places=1, required=False, allow_null=True)
    weightKg = serializers.DecimalField(source='weight_kg', max_digits=5, decimal_places=2, required=False, allow_null=True)
    bmi = serializers.DecimalField(max_digits=4, decimal_places=1, required=False, allow_null=True)
    painScore = serializers.IntegerField(source='pain_score', required=False, allow_null=True)
    recordedAt = serializers.DateTimeField(source='recorded_at', required=False)

    class Meta:
        model = PatientVital
        fields = [
            'id',
            'facilityId',
            'patientId',
            'visitId',
            'ticketId',
            'capturedById',
            'capturedByName',
            'temperatureC',
            'systolicBp',
            'diastolicBp',
            'heartRateBpm',
            'respiratoryRate',
            'spo2Percent',
            'bloodGlucoseMmol',
            'heightCm',
            'weightKg',
            'bmi',
            'painScore',
            'notes',
            'recordedAt',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_active', 'created_at', 'updated_at']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        initial = self.initial_data or {}

        # Temperature aliases
        if 'temperature' in initial and 'temperature_c' not in attrs:
            attrs['temperature_c'] = initial['temperature']
        elif 'temp' in initial and 'temperature_c' not in attrs:
            attrs['temperature_c'] = initial['temp']

        # Systolic aliases
        if 'systolic' in initial and 'systolic_bp' not in attrs:
            attrs['systolic_bp'] = initial['systolic']

        # Diastolic aliases
        if 'diastolic' in initial and 'diastolic_bp' not in attrs:
            attrs['diastolic_bp'] = initial['diastolic']

        # Heart rate / pulse aliases
        if 'pulse' in initial and 'heart_rate_bpm' not in attrs:
            attrs['heart_rate_bpm'] = initial['pulse']
        elif 'heartRate' in initial and 'heart_rate_bpm' not in attrs:
            attrs['heart_rate_bpm'] = initial['heartRate']

        # SpO2 aliases
        if 'spo2' in initial and 'spo2_percent' not in attrs:
            attrs['spo2_percent'] = initial['spo2']
        elif 'oximetry' in initial and 'spo2_percent' not in attrs:
            attrs['spo2_percent'] = initial['oximetry']

        # Blood glucose aliases
        if 'bloodGlucose' in initial and 'blood_glucose_mmol' not in attrs:
            attrs['blood_glucose_mmol'] = initial['bloodGlucose']
        elif 'glucose' in initial and 'blood_glucose_mmol' not in attrs:
            attrs['blood_glucose_mmol'] = initial['glucose']

        attrs = _resolve_patient_for_write(attrs, self.instance, 'patient vital record')
        ticket_id = attrs.get('ticket_id', self.instance.ticket_id if self.instance else None)
        if ticket_id is not None:
            patient = attrs.get('patient', self.instance.patient if self.instance else None)
            facility_id = attrs.get('facility_id', self.instance.facility_id if self.instance else None)
            if not OutpatientTicket.objects.filter(
                pk=ticket_id, patient=patient, facility_id=facility_id, is_active=True,
            ).exists():
                raise serializers.ValidationError({
                    'ticketId': 'Ticket must belong to the selected patient and facility.',
                })
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        if instance.captured_by:
            data['capturedBy'] = {
                'id': instance.captured_by.id,
                'username': instance.captured_by.username,
                'fullName': instance.captured_by.get_full_name() or instance.captured_by.username,
                'role': instance.captured_by.role,
            }
        else:
            data['capturedBy'] = None
        return data

