from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Department, User
from .models import Employee
from .serializers import EmployeeSerializer


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
