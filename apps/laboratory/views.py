from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Facility
from .models import LabRequest, LabResult, LabTest
from .serializers import LabRequestSerializer, LabResultSerializer, LabTestSerializer


class FacilityScopedLaboratoryViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')

		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_requested_facility_id(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		if facility_id is None and self.request.method in ('POST', 'PUT', 'PATCH'):
			facility_id = self.request.data.get('facilityId')
			if facility_id is None:
				facility_id = self.request.data.get('facility_id')

		if facility_id is None:
			return None

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

	def _get_target_facility(self):
		user = self.request.user
		requested_facility_id = self._get_requested_facility_id()

		if user.facility_id:
			if (
				requested_facility_id is not None
				and requested_facility_id != user.facility_id
			):
				raise PermissionDenied('You cannot access laboratory data from another facility.')
			return user.facility

		if user.role == 'admin':
			if requested_facility_id is None:
				raise ValidationError(
					{'facilityId': 'facilityId is required for admin users.'}
				)
			return Facility.objects.filter(id=requested_facility_id).first()

		raise PermissionDenied('Your account is not assigned to a facility.')

	def get_serializer_context(self):
		context = super().get_serializer_context()
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		context['facility'] = facility
		return context


class LabTestViewSet(FacilityScopedLaboratoryViewSet):
	serializer_class = LabTestSerializer
	lookup_field = 'test_id'
	lookup_url_kwarg = 'test_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['category']
	search_fields = ['test_id', 'name', 'category']
	ordering = ['name', '-created_at']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		return LabTest.objects.filter(facility=facility, is_active=True)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		test = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if test.facility_id != facility.id:
			raise PermissionDenied('You cannot modify tests from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete tests from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


class LabRequestViewSet(FacilityScopedLaboratoryViewSet):
	serializer_class = LabRequestSerializer
	lookup_field = 'request_id'
	lookup_url_kwarg = 'request_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['status', 'priority', 'order_date']
	search_fields = ['request_id', 'patient', 'patient_id', 'ordered_by', 'ordered_by_employee_id']
	ordering = ['-order_date', '-created_at']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		queryset = LabRequest.objects.filter(facility=facility, is_active=True)

		patient_id = self.request.query_params.get('patientId')
		if patient_id:
			queryset = queryset.filter(patient_id=patient_id)

		return queryset

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		request_obj = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if request_obj.facility_id != facility.id:
			raise PermissionDenied('You cannot modify requests from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete requests from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])

		result = LabResult.objects.filter(
			facility_id=facility.id,
			request=instance,
			is_active=True,
		).first()
		if result is not None:
			result.is_active = False
			result.save(update_fields=['is_active', 'updated_at'])

	@action(detail=True, methods=['post', 'patch'])
	def start(self, request, request_id=None):
		request_obj = self.get_object()
		if request_obj.status == 'Approved':
			return Response(self.get_serializer(request_obj).data, status=status.HTTP_200_OK)

		request_obj.status = 'In Progress'
		request_obj.save(update_fields=['status', 'updated_at'])
		return Response(self.get_serializer(request_obj).data, status=status.HTTP_200_OK)

	@action(detail=True, methods=['post', 'patch'])
	def approve(self, request, request_id=None):
		request_obj = self.get_object()
		result = LabResult.objects.filter(
			facility_id=request_obj.facility_id,
			request=request_obj,
			is_active=True,
		).first()

		if result is None:
			raise ValidationError({'detail': 'Lab result must be submitted before approval.'})

		approved_by = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email

		request_obj.status = 'Approved'
		request_obj.save(update_fields=['status', 'updated_at'])

		result.status = 'Approved'
		result.approved_by = approved_by
		result.save(update_fields=['status', 'approved_by', 'updated_at'])

		return Response(self.get_serializer(request_obj).data, status=status.HTTP_200_OK)


class LabResultViewSet(FacilityScopedLaboratoryViewSet):
	serializer_class = LabResultSerializer
	lookup_field = 'lab_id'
	lookup_url_kwarg = 'lab_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['status', 'completed_date']
	search_fields = ['lab_id', 'request__patient', 'request__patient_id', 'request__test__name', 'technician']
	ordering = ['-completed_date', '-created_at']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		queryset = LabResult.objects.filter(facility=facility, is_active=True)

		lab_id = self.request.query_params.get('labId')
		if lab_id:
			queryset = queryset.filter(lab_id=lab_id)

		return queryset

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		result = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if result.facility_id != facility.id:
			raise PermissionDenied('You cannot modify results from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete results from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])
