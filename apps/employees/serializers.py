from rest_framework import serializers

from core.models import Department, User
from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    """Serializer that matches frontend naming while persisting Django fields."""

    id = serializers.CharField(source='employee_id', read_only=True)
    role = serializers.ChoiceField(choices=[])
    department = serializers.ChoiceField(choices=[], required=False, allow_blank=True)
    joinDate = serializers.DateField(source='join_date')

    class Meta:
        model = Employee
        fields = [
            'id',
            'name',
            'role',
            'department',
            'email',
            'phone',
            'joinDate',
            'salary',
            'status',
            'shift',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        facility = self._get_request_facility()
        role_choices = sorted(self._get_allowed_roles(facility))
        department_choices = sorted(self._get_allowed_departments(facility))

        self.fields['role'].choices = [(value, value) for value in role_choices]
        self.fields['department'].choices = [(value, value) for value in department_choices]

    def _get_request_facility(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return getattr(user, 'facility', None)

    def _get_allowed_departments(self, facility):
        if facility is None:
            return set()

        return set(
            Department.objects.filter(
                facility=facility,
                is_operational=True,
            ).values_list('name', flat=True)
        )

    def _get_allowed_roles(self, facility):
        if facility is None:
            return set()

        roles = set(
            User.objects.filter(facility=facility)
            .exclude(role='admin')
            .values_list('role', flat=True)
            .distinct()
        )

        # Fallback to configured user roles to avoid blocking setup in new facilities.
        if not roles:
            roles = {value for value, _ in User.ROLE_CHOICES if value != 'admin'}

        return roles

    def validate(self, attrs):
        attrs = super().validate(attrs)

        facility = self._get_request_facility()
        if facility is None:
            raise serializers.ValidationError(
                'Your account is not assigned to a facility.'
            )

        department = attrs.get('department', getattr(self.instance, 'department', ''))
        if department:
            allowed_departments = self._get_allowed_departments(facility)
            if department not in allowed_departments:
                raise serializers.ValidationError(
                    {
                        'department': (
                            'Select a department created for your facility by an administrator.'
                        )
                    }
                )

        role = attrs.get('role', getattr(self.instance, 'role', ''))
        if role:
            allowed_roles = self._get_allowed_roles(facility)
            if role not in allowed_roles:
                raise serializers.ValidationError(
                    {
                        'role': (
                            'Select a role that exists for your facility.'
                        )
                    }
                )

        return attrs

    def create(self, validated_data):
        facility = self._get_request_facility()

        if facility is None:
            raise serializers.ValidationError(
                'Your account is not assigned to a facility.'
            )

        next_number = Employee.objects.filter(facility=facility).count() + 1
        employee_id = f'EMP{next_number:03d}'

        while Employee.objects.filter(facility=facility, employee_id=employee_id).exists():
            next_number += 1
            employee_id = f'EMP{next_number:03d}'

        return Employee.objects.create(
            facility=facility,
            employee_id=employee_id,
            **validated_data,
        )
