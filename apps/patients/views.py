from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	serializer_class = PatientSerializer
	lookup_field = 'patient_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['gender', 'marital_status', 'blood_group', 'is_active']
	search_fields = ['patient_id', 'first_name', 'last_name', 'phone', 'email']
	ordering = ['-created_at']

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})

		try:
			return int(facility_id)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': 'facilityId must be a valid integer.'})

	def _get_facility_id_from_body(self):
		facility_id = self.request.data.get('facilityId')
		if facility_id is None:
			facility_id = self.request.data.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required in request body.'})

		try:
			return int(facility_id)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': 'facilityId must be a valid integer.'})

	def _enforce_user_facility_access(self, facility_id):
		user = self.request.user

		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access patients from another facility.')

		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		return Patient.objects.filter(facility_id=facility_id, is_active=True)

	def perform_create(self, serializer):
		facility_id = self._get_facility_id_from_body()
		self._enforce_user_facility_access(facility_id)
		serializer.save(facility_id=facility_id)

	def perform_update(self, serializer):
		patient = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		if patient.facility_id != facility_id:
			raise PermissionDenied('You cannot modify patients from another facility.')

		if 'facilityId' not in self.request.data and 'facility_id' not in self.request.data:
			serializer.save()
			return

		serializer.save()

	def perform_destroy(self, instance):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		if instance.facility_id != facility_id:
			raise PermissionDenied('You cannot delete patients from another facility.')
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])
