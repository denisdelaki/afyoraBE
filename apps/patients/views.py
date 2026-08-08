from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import EhrRecord, Patient, PatientVisit
from .serializers import EhrRecordSerializer, PatientSerializer, PatientVisitSerializer


class PatientViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	serializer_class = PatientSerializer
	lookup_field = 'patient_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['gender', 'marital_status', 'blood_group', 'is_active']
	search_fields = ['patient_id', 'first_name', 'last_name', 'phone', 'email']
	ordering = ['-created_at']

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')

		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

	def _get_facility_id_from_body(self):
		facility_id = self.request.data.get('facilityId')
		if facility_id is None:
			facility_id = self.request.data.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required in request body.'})

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

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


class PatientVisitViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	serializer_class = PatientVisitSerializer
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	search_fields = ['patient__patient_id', 'served_by', 'diagnosis', 'prescription', 'what_happened']
	ordering = ['-visit_date', '-created_at']

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')

		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

	def _get_facility_id_from_body(self):
		facility_id = self.request.data.get('facilityId')
		if facility_id is None:
			facility_id = self.request.data.get('facility_id')

		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required in request body.'})

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

	def _enforce_user_facility_access(self, facility_id):
		user = self.request.user

		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access visits from another facility.')

		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		queryset = PatientVisit.objects.filter(facility_id=facility_id, is_active=True)

		patient_id = self.request.query_params.get('patientId')
		if patient_id:
			queryset = queryset.filter(patient__patient_id=patient_id)

		return queryset

	def perform_create(self, serializer):
		facility_id = self._get_facility_id_from_body()
		self._enforce_user_facility_access(facility_id)
		serializer.save(facility_id=facility_id)

	def perform_update(self, serializer):
		visit = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		if visit.facility_id != facility_id:
			raise PermissionDenied('You cannot modify visits from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		if instance.facility_id != facility_id:
			raise PermissionDenied('You cannot delete visits from another facility.')

		linked_prescription = instance.prescription_record

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])

		if linked_prescription is not None:
			is_used_elsewhere = PatientVisit.objects.filter(
				prescription_record=linked_prescription,
				is_active=True,
			).exclude(id=instance.id).exists()

			if not is_used_elsewhere and linked_prescription.is_active:
				linked_prescription.is_active = False
				linked_prescription.save(update_fields=['is_active', 'updated_at'])


class EhrRecordViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	serializer_class = EhrRecordSerializer
	lookup_url_kwarg = 'ehr_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	search_fields = ['diagnosis', 'symptoms', 'treatment', 'doctor', 'doctor_notes']
	ordering = ['-date', '-created_at']

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')
		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})
		return self._parse_facility_id(facility_id, 'facilityId must be a valid integer.')

	def _get_facility_id_from_body(self):
		facility_id = self.request.data.get('facilityId')
		if facility_id is None:
			facility_id = self.request.data.get('facility_id')
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required in request body.'})
		return self._parse_facility_id(facility_id, 'facilityId must be a valid integer.')

	def _enforce_user_facility_access(self, facility_id):
		user = self.request.user
		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access EHR records from another facility.')
		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def _get_patient_from_path(self, facility_id):
		patient_id = self.kwargs.get('patient_id')
		patient = Patient.objects.filter(
			patient_id=patient_id,
			facility_id=facility_id,
			is_active=True,
		).first()
		if patient is None:
			raise ValidationError({'patientId': 'Patient not found for the provided facilityId.'})
		return patient

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		patient = self._get_patient_from_path(facility_id)
		return EhrRecord.objects.filter(
			facility_id=facility_id,
			patient=patient,
			is_active=True,
		)

	def perform_create(self, serializer):
		facility_id = self._get_facility_id_from_body()
		self._enforce_user_facility_access(facility_id)
		patient = self._get_patient_from_path(facility_id)
		user = self.request.user
		doctor_name = f"{user.first_name} {user.last_name}".strip() or user.email
		serializer.save(facility_id=facility_id, patient=patient, doctor=doctor_name)

	def perform_update(self, serializer):
		record = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		if record.facility_id != facility_id:
			raise PermissionDenied('You cannot modify EHR records from another facility.')
		serializer.save()

	def perform_destroy(self, instance):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		if instance.facility_id != facility_id:
			raise PermissionDenied('You cannot delete EHR records from another facility.')
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])



class PatientVisitHistoryViewSet(PatientVisitViewSet):
	lookup_url_kwarg = 'visit_id'

	def _get_patient_from_path(self, facility_id):
		patient_id = self.kwargs.get('patient_id')
		patient = Patient.objects.filter(
			patient_id=patient_id,
			facility_id=facility_id,
			is_active=True,
		).first()

		if patient is None:
			raise ValidationError(
				{'patientId': 'Patient not found for the provided facilityId.'}
			)

		return patient

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		patient = self._get_patient_from_path(facility_id)

		return PatientVisit.objects.filter(
			facility_id=facility_id,
			patient=patient,
			is_active=True,
		)

	def create(self, request, *args, **kwargs):
		facility_id = self._get_facility_id_from_body()
		self._enforce_user_facility_access(facility_id)
		patient = self._get_patient_from_path(facility_id)

		payload = request.data.copy()
		payload['facilityId'] = facility_id
		payload['patientId'] = patient.patient_id

		serializer = self.get_serializer(data=payload)
		serializer.is_valid(raise_exception=True)
		serializer.save(facility_id=facility_id, patient=patient)
		headers = self.get_success_headers(serializer.data)

		return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
