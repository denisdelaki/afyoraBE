import logging

from django.db import transaction

from rest_framework import serializers

from core.models import Department, User
from .models import Employee
from .utils import generate_temp_password, send_employee_credentials

logger = logging.getLogger(__name__)


class EmployeeSerializer(serializers.ModelSerializer):
    """Serializer that matches frontend naming while persisting Django fields."""

    id = serializers.CharField(source='employee_id', read_only=True)
    role = serializers.CharField()
    department = serializers.CharField(required=False, allow_blank=True)
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
        role_choices = sorted(self._get_allowed_roles())
        department_choices = sorted(self._get_allowed_departments(facility))

        # Attach metadata used by browsable API and schema clients.
        self.fields['role'].help_text = f"Allowed roles: {', '.join(role_choices)}"
        if department_choices:
            self.fields['department'].help_text = (
                "Provide a department name or numeric department ID "
                f"from your facility: {', '.join(department_choices)}"
            )

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

    def _get_allowed_roles(self):
        # Use configured system roles directly so creation is not blocked by
        # which roles currently exist as users in a facility.
        return {value for value, _ in User.ROLE_CHOICES if value != 'admin'}

    def _normalize_role(self, role_value):
        if role_value is None:
            return role_value

        role_value = str(role_value).strip()
        if not role_value:
            return role_value

        allowed_roles = self._get_allowed_roles()
        if role_value in allowed_roles:
            return role_value

        normalized_input = role_value.lower().replace('-', '_').replace(' ', '_')
        if normalized_input in allowed_roles:
            return normalized_input

        label_to_value = {
            label.lower().replace('-', '_').replace(' ', '_'): value
            for value, label in User.ROLE_CHOICES
            if value != 'admin'
        }
        if normalized_input in label_to_value:
            return label_to_value[normalized_input]

        raise serializers.ValidationError(
            (
                f'"{role_value}" is not a valid role. '
                f"Use one of: {', '.join(sorted(allowed_roles))}."
            )
        )

    def _normalize_department(self, facility, department_value):
        if department_value in (None, ''):
            return ''

        department_value = str(department_value).strip()
        if not department_value:
            return ''

        departments_qs = Department.objects.filter(
            facility=facility,
            is_operational=True,
        )

        # During initial setup a facility may not have departments yet.
        # Allow free-text values so employee creation is not blocked.
        if not departments_qs.exists():
            if department_value.isdigit():
                raise serializers.ValidationError(
                    'No operational departments exist yet; provide a department name.'
                )
            return department_value

        if department_value.isdigit():
            department_obj = departments_qs.filter(id=int(department_value)).first()
            if department_obj is None:
                raise serializers.ValidationError(
                    'Select a department ID that belongs to your facility and is operational.'
                )
            return department_obj.name

        department_obj = departments_qs.filter(name=department_value).first()
        if department_obj is not None:
            return department_obj.name

        raise serializers.ValidationError(
            'Select a department created for your facility by an administrator.'
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        facility = self._get_request_facility()
        if facility is None:
            raise serializers.ValidationError(
                'Your account is not assigned to a facility.'
            )

        role = attrs.get('role', getattr(self.instance, 'role', ''))
        if role:
            attrs['role'] = self._normalize_role(role)

        if 'department' in attrs:
            attrs['department'] = self._normalize_department(
                facility,
                attrs.get('department'),
            )
        else:
            existing_department = getattr(self.instance, 'department', '')
            if existing_department:
                attrs['department'] = self._normalize_department(
                    facility,
                    existing_department,
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

        with transaction.atomic():
            employee = Employee.objects.create(
                facility=facility,
                employee_id=employee_id,
                **validated_data,
            )

            email = employee.email.strip() if employee.email else ''
            if email:
                self._provision_user_account(employee, facility, employee_id)

        return employee

    def update(self, instance, validated_data):
        facility = self._get_request_facility()
        with transaction.atomic():
            employee = super().update(instance, validated_data)
            email = employee.email.strip() if employee.email else ''
            if email and facility is not None:
                self._provision_user_account(employee, facility, employee.employee_id)
        return employee

    def _provision_user_account(self, employee, facility, employee_id):
        """Create a User login account and email credentials to the employee."""
        email = employee.email.strip()

        # Use email as username; skip if an account already exists for this email.
        if User.objects.filter(username=email).exists():
            logger.warning(
                "User account already exists for %s — skipping credential email. "
                "Use the resend-credentials endpoint to issue a new password.",
                email,
            )
            return None

        role = employee.role
        # Map employee role to a valid User.ROLE_CHOICES value.
        allowed_roles = {value for value, _ in User.ROLE_CHOICES}
        user_role = role if role in allowed_roles else 'staff'

        name_parts = employee.name.strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        temp_password = generate_temp_password()

        user = User.objects.create_user(
            username=email,
            email=email,
            password=temp_password,
            first_name=first_name,
            last_name=last_name,
            facility=facility,
            role=user_role,
            employee_id=employee_id,
            department=employee.department,
            phone=employee.phone,
            must_change_password=True,
        )

        def _send():
            try:
                send_employee_credentials(
                    employee_name=employee.name,
                    email=email,
                    username=email,
                    password=temp_password,
                    facility_name=facility.name,
                )
            except Exception:
                logger.exception(
                    "Failed to send credential email to %s. Account was still created.", email
                )

        transaction.on_commit(_send)
        return user
