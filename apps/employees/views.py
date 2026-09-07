from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils import timezone
from decimal import Decimal

from core.models import Department, User
from core.utils import check_module_permission
from .models import Employee, EmployeeAttendance
from .serializers import EmployeeSerializer, EmployeeAttendanceSerializer
from .utils import generate_temp_password, send_employee_credentials


class EmployeeViewSet(viewsets.ModelViewSet):
	"""CRUD endpoints for employees scoped to the logged-in facility."""

	permission_classes = [IsAuthenticated]
	serializer_class = EmployeeSerializer
	http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
	filterset_fields = ['role', 'department', 'status', 'shift']
	search_fields = ['name', 'email', 'employee_id']
	ordering = ['-created_at']

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			# Allow any authenticated employee to manage their personal attendance
			if self.action in ['clock_in', 'clock_out', 'my_attendance']:
				return
			
			# Require read access for facility-wide attendance log
			if self.action == 'attendance':
				check_module_permission(request.user, 'employees', action='read')
				return
				
			check_module_permission(request.user, 'employees', request=request)

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
		email = (employee.email or '').strip().lower()

		if not email:
			raise ValidationError({'email': 'Employee does not have an email address configured.'})

		user = User.objects.filter(username__iexact=email).first()
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

	@action(detail=False, methods=['post'], url_path='clock-in')
	def clock_in(self, request):
		"""Clock in the current employee."""
		user = request.user
		if not user.employee_id:
			raise PermissionDenied('No employee record associated with this user.')
		
		employee = Employee.objects.filter(employee_id=user.employee_id, facility=user.facility).first()
		if not employee:
			raise PermissionDenied('Employee record not found.')
		
		today = timezone.localdate()
		attendance = EmployeeAttendance.objects.filter(employee=employee, date=today).first()
		
		if attendance:
			if attendance.status == 'clocked_in':
				return Response({'detail': 'Already clocked in for today.'}, status=status.HTTP_400_BAD_REQUEST)
			else:
				return Response({'detail': f'Already clocked out or absent today. Current status: {attendance.status}'}, status=status.HTTP_400_BAD_REQUEST)

		attendance = EmployeeAttendance.objects.create(
			facility=user.facility,
			employee=employee,
			user=user,
			date=today,
			clock_in=timezone.now(),
			status='clocked_in'
		)
		
		serializer = EmployeeAttendanceSerializer(attendance)
		return Response(serializer.data, status=status.HTTP_201_CREATED)

	@action(detail=False, methods=['post'], url_path='clock-out')
	def clock_out(self, request):
		"""Clock out the current employee."""
		user = request.user
		if not user.employee_id:
			raise PermissionDenied('No employee record associated with this user.')
		
		employee = Employee.objects.filter(employee_id=user.employee_id, facility=user.facility).first()
		if not employee:
			raise PermissionDenied('Employee record not found.')
		
		today = timezone.localdate()
		attendance = EmployeeAttendance.objects.filter(employee=employee, date=today, status='clocked_in').first()
		
		if not attendance:
			return Response({'detail': 'No active clock-in session found for today.'}, status=status.HTTP_400_BAD_REQUEST)

		clock_out_time = timezone.now()
		attendance.clock_out = clock_out_time
		attendance.status = 'clocked_out'
		
		duration = clock_out_time - attendance.clock_in
		hours = Decimal(duration.total_seconds()) / Decimal(3600)
		attendance.hours_worked = hours.quantize(Decimal('0.01'))
		attendance.save()
		
		serializer = EmployeeAttendanceSerializer(attendance)
		return Response(serializer.data, status=status.HTTP_200_OK)

	@action(detail=False, methods=['get'], url_path='my-attendance')
	def my_attendance(self, request):
		"""Get personal attendance log."""
		user = request.user
		if not user.employee_id:
			raise PermissionDenied('No employee record associated with this user.')
		
		employee = Employee.objects.filter(employee_id=user.employee_id, facility=user.facility).first()
		if not employee:
			raise PermissionDenied('Employee record not found.')
		
		attendances = EmployeeAttendance.objects.filter(employee=employee).order_by('-date')
		page = self.paginate_queryset(attendances)
		if page is not None:
			serializer = EmployeeAttendanceSerializer(page, many=True)
			return self.get_paginated_response(serializer.data)

		serializer = EmployeeAttendanceSerializer(attendances, many=True)
		return Response(serializer.data)

	@action(detail=False, methods=['get'])
	def attendance(self, request):
		"""Admin/HR endpoint to query facility-wide attendance records."""
		user = request.user
		if not user.facility:
			raise PermissionDenied('Your account is not assigned to a facility.')
		
		# Explicitly restrict to HR, facility_admin, and admin
		if user.role not in ['hr', 'facility_admin', 'admin']:
			raise PermissionDenied('Only HR and facility administrators can view the facility-wide attendance log.')
		
		attendances = EmployeeAttendance.objects.filter(facility=user.facility).order_by('-date', '-clock_in')
		
		date = request.query_params.get('date')
		if date:
			attendances = attendances.filter(date=date)
		
		employee_id = request.query_params.get('employee_id')
		if employee_id:
			attendances = attendances.filter(employee__employee_id=employee_id)
		
		page = self.paginate_queryset(attendances)
		if page is not None:
			serializer = EmployeeAttendanceSerializer(page, many=True)
			return self.get_paginated_response(serializer.data)

		serializer = EmployeeAttendanceSerializer(attendances, many=True)
		return Response(serializer.data)
