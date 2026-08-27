from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils import check_module_permission
from .models import Appointment
from .serializers import AppointmentSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'appointments'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY)
	serializer_class = AppointmentSerializer
	lookup_field = 'appointment_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
	filterset_fields = ['status', 'doctor', 'department', 'date']
	search_fields = ['appointment_id', 'patient__patient_id', 'patient__first_name', 'patient__last_name']
	ordering = ['date', 'time', '-created_at']

	def _parse_facility_id(self, value):
		if value is None:
			return None

		value = str(value).strip().rstrip('/')
		if not value:
			return None

		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': 'facilityId must be a valid integer.'})

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		facility_id = self._parse_facility_id(facility_id)
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})

		return facility_id

	def _enforce_user_facility_access(self, facility_id):
		user = self.request.user

		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access appointments from another facility.')

		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		queryset = Appointment.objects.filter(facility_id=facility_id, is_active=True).select_related('patient')
		patient_id = self.request.query_params.get('patientId')
		if patient_id is None:
			patient_id = self.request.query_params.get('patient_id')

		if patient_id:
			queryset = queryset.filter(patient__patient_id=patient_id)

		return queryset

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['facility_id'] = self._get_facility_id_from_query()
		return context

	def perform_create(self, serializer):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		serializer.save()

	def perform_update(self, serializer):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		appointment = self.get_object()
		if appointment.facility_id != facility_id:
			raise PermissionDenied('You cannot modify appointments from another facility.')

		serializer.save()

	@action(detail=True, methods=['patch'])
	def cancel(self, request, appointment_id=None):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		appointment = self.get_object()
		if appointment.facility_id != facility_id:
			raise PermissionDenied('You cannot cancel appointments from another facility.')

		serializer = self.get_serializer(
			appointment,
			data={'status': 'Cancelled'},
			partial=True,
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()

		return Response(serializer.data)
