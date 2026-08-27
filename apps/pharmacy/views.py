from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from core.models import Facility
from core.utils import check_module_permission
from .models import Drug, Prescription
from .serializers import DrugSerializer, PrescriptionSerializer


class FacilityScopedPharmacyViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'pharmacy'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY)


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
				raise PermissionDenied('You cannot access pharmacy data from another facility.')
			return user.facility

		if user.role == 'admin':
			if requested_facility_id is None:
				raise ValidationError(
					{'facilityId': 'facilityId query param is required for admin users.'}
				)
			return Facility.objects.filter(id=requested_facility_id).first()

		raise PermissionDenied('Your account is not assigned to a facility.')


class DrugViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = DrugSerializer
	lookup_field = 'drug_id'
	lookup_url_kwarg = 'drug_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['category', 'manufacturer']
	search_fields = ['drug_id', 'name', 'category', 'manufacturer']
	ordering = ['-created_at']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		return Drug.objects.filter(facility=facility, is_active=True)

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				'items': serializer.data,
				'count': queryset.count(),
			},
			status=status.HTTP_200_OK,
		)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		drug = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if drug.facility_id != facility.id:
			raise PermissionDenied('You cannot modify drugs from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete drugs from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


class PrescriptionViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = PrescriptionSerializer
	lookup_field = 'prescription_id'
	lookup_url_kwarg = 'prescription_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['status', 'date']
	search_fields = ['prescription_id', 'patient_id', 'doctor_id', 'status']
	ordering = ['-date', '-created_at']

	def _query_prescriptions(self, include_inactive=False):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		queryset = Prescription.objects.filter(facility=facility)
		if not include_inactive:
			queryset = queryset.filter(is_active=True)

		return queryset

	def get_object(self):
		include_inactive = self.action == 'destroy'
		queryset = self.filter_queryset(
			self._query_prescriptions(include_inactive=include_inactive)
		)
		lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
		lookup_value = self.kwargs.get(lookup_url_kwarg)

		instance = None
		if isinstance(lookup_value, str) and lookup_value.isdigit():
			instance = queryset.filter(pk=int(lookup_value)).first()

		if instance is None:
			instance = queryset.filter(**{self.lookup_field: lookup_value}).first()

		if instance is None:
			raise Http404

		self.check_object_permissions(self.request, instance)
		return instance

	def get_queryset(self):
		return self._query_prescriptions(include_inactive=False)

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				'items': serializer.data,
				'count': queryset.count(),
			},
			status=status.HTTP_200_OK,
		)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		prescription = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if prescription.facility_id != facility.id:
			raise PermissionDenied('You cannot modify prescriptions from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete prescriptions from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])

	@action(detail=True, methods=['post', 'patch'])
	def dispense(self, request, prescription_id=None):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		prescription = self.get_object()
		if prescription.facility_id != facility.id:
			raise PermissionDenied('You cannot dispense prescriptions from another facility.')

		with transaction.atomic():
			locked_prescription = (
				Prescription.objects.select_for_update()
				.filter(pk=prescription.pk, facility_id=facility.id)
				.first()
			)

			if locked_prescription is None:
				raise Http404

			if locked_prescription.status == 'Dispensed':
				serializer = self.get_serializer(locked_prescription)
				return Response(serializer.data, status=status.HTTP_200_OK)

			today = timezone.localdate()
			drug_updates = []
			for index, item in enumerate(locked_prescription.drugs or []):
				if not isinstance(item, dict):
					raise ValidationError(
						{'drugs': f'Invalid drug payload at index {index}.'}
					)

				drug_id = str(item.get('id') or '').strip()
				drug_name = str(item.get('name') or '').strip()
				quantity = item.get('quantity')

				try:
					quantity = int(quantity)
				except (TypeError, ValueError):
					raise ValidationError(
						{'drugs': f'Invalid quantity for drug at index {index}.'}
					)

				if quantity <= 0:
					raise ValidationError(
						{'drugs': f'Quantity must be greater than zero at index {index}.'}
					)

				drug_qs = Drug.objects.select_for_update().filter(
					facility_id=facility.id,
					is_active=True,
				)

				drug = None
				if drug_id:
					drug = drug_qs.filter(drug_id=drug_id).first()

				if drug is None and drug_name:
					drug = drug_qs.filter(name__iexact=drug_name).first()

				if drug is None:
					raise ValidationError(
						{'drugs': f'Drug not found at index {index}.'}
					)

				if drug.expiry_date and drug.expiry_date < today:
					raise ValidationError(
						{'drugs': f'Drug {drug.name} is expired and cannot be dispensed.'}
					)

				if drug.stock < quantity:
					raise ValidationError(
						{
							'drugs': (
								f'Insufficient stock for {drug.name}. '
								f'Available: {drug.stock}, requested: {quantity}.'
							)
						}
					)

				drug_updates.append((drug, quantity))

			for drug, quantity in drug_updates:
				drug.stock -= quantity
				drug.save(update_fields=['stock', 'updated_at'])

			locked_prescription.status = 'Dispensed'
			locked_prescription.save(update_fields=['status', 'updated_at'])

		serializer = self.get_serializer(locked_prescription)
		return Response(serializer.data, status=status.HTTP_200_OK)
