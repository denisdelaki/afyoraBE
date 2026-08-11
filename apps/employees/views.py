from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Department, User
from .models import Employee
from .serializers import EmployeeSerializer
from .utils import generate_temp_password, send_employee_credentials


class EmployeeViewSet(viewsets.ModelViewSet):
	"""CRUD endpoints for employees scoped to the logged-in facility."""

	permission_classes = [IsAuthenticated]
	serializer_class = EmployeeSerializer
	http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
	filterset_fields = ['role', 'department', 'status', 'shift']
	search_fields = ['name', 'email', 'employee_id']
	ordering = ['-created_at']

	def get_queryset(self):
		user = self.request.user
		requested_facility_id = self.request.query_params.get('facility_id')
		if requested_facility_id is None:
			requested_facility_id = self.request.query_params.get('facility')

		if requested_facility_id is not None:
			try:
				requested_facility_id = int(requested_facility_id)
			except (TypeError, ValueError):
				raise ValidationError(
					{'facility_id': 'facility_id must be a valid integer.'}
				)

		if user.facility_id:
			if (
				requested_facility_id is not None
				and requested_facility_id != user.facility_id
			):
				raise PermissionDenied(
					'You cannot access employees from another facility.'
				)

			return Employee.objects.filter(facility_id=user.facility_id)

		if user.role == 'admin' and requested_facility_id is not None:
			return Employee.objects.filter(facility_id=requested_facility_id)

		return Employee.objects.none()

	def perform_create(self, serializer):
		user = self.request.user

		if not user.facility_id:
			raise PermissionDenied('Your account is not assigned to a facility.')

		# Serializer create() assigns facility from request.user.
		serializer.save()

	def perform_update(self, serializer):
		employee = self.get_object()
		user = self.request.user

		if employee.facility_id != user.facility_id:
			raise PermissionDenied('You cannot modify employees from another facility.')

		serializer.save()

	@action(detail=False, methods=['get'])
	def options(self, request):
		"""Return role and department selections scoped to requester's facility."""
		facility = request.user.facility

		if facility is None:
			return Response({'roles': [], 'departments': []})

		roles = list(
			User.objects.filter(facility=facility)
			.exclude(role='admin')
			.values_list('role', flat=True)
			.distinct()
		)

		if not roles:
			roles = [value for value, _ in User.ROLE_CHOICES if value != 'admin']

		departments = list(
			Department.objects.filter(facility=facility, is_operational=True)
			.values_list('name', flat=True)
			.order_by('name')
		)

		return Response(
			{
				'roles': roles,
				'departments': departments,
			}
		)

	@action(detail=True, methods=['post'])
	def resend_credentials(self, request, pk=None):
		"""Reset password to a temporary password and resend credentials email."""
		employee = self.get_object()
		email = (employee.email or '').strip()

		if not email:
			raise ValidationError({'email': 'Employee does not have an email address configured.'})

		user = User.objects.filter(username=email).first()
		temp_password = generate_temp_password()

		if user is None:
			name_parts = employee.name.strip().split(" ", 1)
			first_name = name_parts[0]
			last_name = name_parts[1] if len(name_parts) > 1 else ''
			user_role = employee.role if employee.role in {v for v, _ in User.ROLE_CHOICES} else 'staff'

			user = User.objects.create_user(
				username=email,
				email=email,
				password=temp_password,
				first_name=first_name,
				last_name=last_name,
				facility=employee.facility,
				role=user_role,
				employee_id=employee.employee_id,
				department=employee.department,
				phone=employee.phone,
				must_change_password=True,
			)
		else:
			user.set_password(temp_password)
			user.must_change_password = True
			user.save(update_fields=['password', 'must_change_password'])

		send_employee_credentials(
			employee_name=employee.name,
			email=email,
			username=email,
			password=temp_password,
			facility_name=employee.facility.name,
		)

		return Response({'detail': f'Credentials successfully sent to {email}.'}, status=status.HTTP_200_OK)
