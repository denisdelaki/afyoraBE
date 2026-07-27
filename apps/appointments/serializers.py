from rest_framework import serializers

from patients.models import Patient
from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='appointment_id', read_only=True)
    patientId = serializers.CharField(required=False)
    firstName = serializers.CharField(source='patient.first_name', read_only=True)
    lastName = serializers.CharField(source='patient.last_name', read_only=True)
    time = serializers.TimeField(format='%H:%M', input_formats=['%H:%M', '%H:%M:%S'])

    class Meta:
        model = Appointment
        fields = [
            'id',
            'patientId',
            'firstName',
            'lastName',
            'date',
            'time',
            'doctor',
            'department',
            'status',
        ]
        read_only_fields = ['id', 'firstName', 'lastName']

    def validate(self, attrs):
        attrs = super().validate(attrs)

        facility_id = self.context.get('facility_id')
        if facility_id is None:
            raise serializers.ValidationError({'facilityId': 'facilityId is required.'})

        patient_identifier = attrs.pop('patientId', None)
        if self.instance is None and not patient_identifier:
            raise serializers.ValidationError({'patientId': 'patientId is required.'})

        if patient_identifier:
            patient = Patient.objects.filter(
                facility_id=facility_id,
                patient_id=patient_identifier,
                is_active=True,
            ).first()
            if patient is None:
                raise serializers.ValidationError(
                    {'patientId': 'No active patient found for this facility.'}
                )
            attrs['patient'] = patient

        if self.instance is not None and 'patient' not in attrs:
            attrs['patient'] = self.instance.patient

        # Create-only guard: prevent booking the same doctor twice on the same day.
        if self.instance is None:
            doctor = attrs.get('doctor')
            date = attrs.get('date')
            if doctor and date:
                has_conflict = Appointment.objects.filter(
                    facility_id=facility_id,
                    doctor=doctor,
                    date=date,
                    is_active=True,
                ).exists()
                if has_conflict:
                    raise serializers.ValidationError(
                        {
                            'doctor': (
                                'This doctor already has an appointment on this day. '
                                'Please reschedule to another day.'
                            )
                        }
                    )

        # Update-only guard: enforce slot availability only when rescheduling.
        if self.instance is not None and any(
            field in attrs for field in ['doctor', 'date', 'time']
        ):
            doctor = attrs.get('doctor', self.instance.doctor)
            date = attrs.get('date', self.instance.date)
            time = attrs.get('time', self.instance.time)
            if doctor and date and time:
                has_conflict = Appointment.objects.filter(
                    facility_id=facility_id,
                    doctor=doctor,
                    date=date,
                    time=time,
                    is_active=True,
                ).exclude(pk=self.instance.pk).exists()
                if has_conflict:
                    raise serializers.ValidationError(
                        {
                            'doctor': (
                                'This doctor already has an appointment at that date and time. '
                                'Please reschedule to another time.'
                            )
                        }
                    )

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['patientId'] = instance.patient.patient_id
        return data

    def create(self, validated_data):
        facility_id = self.context.get('facility_id')
        next_number = Appointment.objects.filter(facility_id=facility_id).count() + 1
        appointment_id = f'APT{next_number:04d}'

        while Appointment.objects.filter(
            facility_id=facility_id,
            appointment_id=appointment_id,
        ).exists():
            next_number += 1
            appointment_id = f'APT{next_number:04d}'

        return Appointment.objects.create(
            facility_id=facility_id,
            appointment_id=appointment_id,
            **validated_data,
        )
