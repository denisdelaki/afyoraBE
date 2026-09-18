from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.models import AuditLog, User
from core.utils import check_module_permission
from core.compliance import log_concept_provenance
from .models import AllergyItem, CpoeOrder, EhrRecord, OutpatientTicket, OutpatientTicketMovement, Patient, PatientVisit, ProblemItem
from .serializers import (
	AllergyItemSerializer,
	CpoeOrderSerializer,
	EhrRecordSerializer,
	OutpatientTicketSerializer,
	PatientSerializer,
	PatientVisitSerializer,
	ProblemItemSerializer,
)


class PatientViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'patients'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY, request=request)
	serializer_class = PatientSerializer
	lookup_field = 'patient_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['gender', 'marital_status', 'blood_group', 'is_active']
	search_fields = [
		'patient_id',
		'national_id_or_birth_certificate',
		'first_name',
		'last_name',
		'phone',
		'email',
	]
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
		visit = serializer.save(facility_id=facility_id)
		# DHA: write provenance log if a coded concept was stored
		if visit.diagnosis_code:
			log_concept_provenance(
				user=self.request.user,
				facility=visit.facility,
				record_type='visit',
				record_id=str(visit.id),
				concept={
					'code_system': visit.diagnosis_system,
					'code': visit.diagnosis_code,
					'display': visit.diagnosis_text or visit.diagnosis,
				},
			)
			AuditLog.objects.create(
				facility=visit.facility,
				user=self.request.user,
				action='create',
				model_name='PatientVisit',
				object_id=str(visit.id),
				description=(
					f'Visit record created for patient {visit.patient.patient_id}. '
					f'Coded diagnosis: [{visit.diagnosis_system}:{visit.diagnosis_code}] '
					f'{visit.diagnosis_text or visit.diagnosis}'
				),
				ip_address=self.request.META.get('REMOTE_ADDR'),
			)

	def perform_update(self, serializer):
		visit_before = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)

		if visit_before.facility_id != facility_id:
			raise PermissionDenied('You cannot modify visits from another facility.')

		visit = serializer.save()
		# DHA: write provenance log if a coded concept was updated
		if visit.diagnosis_code:
			log_concept_provenance(
				user=self.request.user,
				facility=visit.facility,
				record_type='visit',
				record_id=str(visit.id),
				concept={
					'code_system': visit.diagnosis_system,
					'code': visit.diagnosis_code,
					'display': visit.diagnosis_text or visit.diagnosis,
				},
			)
			AuditLog.objects.create(
				facility=visit.facility,
				user=self.request.user,
				action='update',
				model_name='PatientVisit',
				object_id=str(visit.id),
				description=(
					f'Visit record updated for patient {visit.patient.patient_id}. '
					f'Coded diagnosis: [{visit.diagnosis_system}:{visit.diagnosis_code}] '
					f'{visit.diagnosis_text or visit.diagnosis}'
				),
				ip_address=self.request.META.get('REMOTE_ADDR'),
			)

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


class OutpatientTicketViewSet(viewsets.ModelViewSet):
	MODULE_KEY = 'visit_queue'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY, request=request)
	"""A small, explicit queue for moving an outpatient through a facility."""

	permission_classes = [IsAuthenticated]
	serializer_class = OutpatientTicketSerializer
	http_method_names = ['get', 'post', 'head', 'options']
	search_fields = ['ticket_number', 'patient__patient_id', 'patient__first_name', 'patient__last_name']
	ordering = ['created_at']

	ROLE_BY_DESTINATION = {
		'reception': {'receptionist'},
		'consultation': {'doctor', 'nurse'},
		'laboratory': {'lab_technician'},
		'radiology': {'radiologist'},
		'pharmacy': {'pharmacist'},
		'billing': {'accountant'},
	}
	PRIVILEGED_ROLES = {'admin', 'facility_admin', 'manager'}

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')
		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_facility_id(self, from_body=False):
		values = self.request.data if from_body else self.request.query_params
		facility_id = values.get('facilityId') or values.get('facility_id')
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required.'})
		return self._parse_facility_id(facility_id, 'facilityId must be a valid integer.')

	def _enforce_facility_access(self, facility_id):
		user = self.request.user
		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access tickets from another facility.')
		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def get_queryset(self):
		facility_id = self._get_facility_id()
		self._enforce_facility_access(facility_id)
		queryset = OutpatientTicket.objects.filter(facility_id=facility_id, is_active=True).select_related('patient', 'assigned_to')
		for field in ('destination', 'status', 'assignedTo'):
			value = self.request.query_params.get(field)
			if value:
				queryset = queryset.filter(**{'assigned_to_id' if field == 'assignedTo' else field: value})
		return queryset

	def _next_ticket_number(self, facility_id):
		prefix = f"OP-{timezone.localdate():%Y%m%d}-"
		existing = OutpatientTicket.objects.filter(facility_id=facility_id, ticket_number__startswith=prefix)
		return f'{prefix}{existing.count() + 1:03d}'

	def create(self, request, *args, **kwargs):
		facility_id = self._get_facility_id(from_body=True)
		self._enforce_facility_access(facility_id)
		if request.user.role not in {'admin', 'facility_admin', 'manager', 'receptionist', 'nurse'}:
			raise PermissionDenied('Only reception staff can create outpatient tickets.')
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		# A retry makes the simple daily number safe when two receptionists create at once.
		for _ in range(3):
			try:
				with transaction.atomic():
					ticket = serializer.save(
						facility_id=facility_id,
						ticket_number=self._next_ticket_number(facility_id),
						created_by=request.user,
					)
					OutpatientTicketMovement.objects.create(
						ticket=ticket, to_destination=ticket.destination,
						forwarded_by=request.user, assigned_to=ticket.assigned_to,
						notes=ticket.notes,
					)
				break
			except IntegrityError:
				continue
		else:
			raise ValidationError({'detail': 'Unable to allocate a ticket number. Please retry.'})
		return Response(self.get_serializer(ticket).data, status=status.HTTP_201_CREATED)

	def _can_work_ticket(self, ticket):
		user = self.request.user
		if user.role in self.PRIVILEGED_ROLES:
			return True
		if ticket.assigned_to_id:
			return ticket.assigned_to_id == user.id
		return user.role in self.ROLE_BY_DESTINATION[ticket.destination]

	@action(detail=True, methods=['post'])
	def call(self, request, pk=None):
		ticket = self.get_object()
		if ticket.status != 'waiting':
			raise ValidationError({'status': 'Only waiting tickets can be called.'})
		if not self._can_work_ticket(ticket):
			raise PermissionDenied('This ticket is not in your queue.')
		ticket.status = 'called'
		ticket.called_by = request.user
		ticket.save(update_fields=['status', 'called_by', 'updated_at'])
		return Response(self.get_serializer(ticket).data)

	@action(detail=True, methods=['post'])
	def forward(self, request, pk=None):
		ticket = self.get_object()
		if ticket.status != 'called':
			raise ValidationError({'status': 'Call the ticket before forwarding it.'})
		if ticket.called_by_id != request.user.id and request.user.role not in self.PRIVILEGED_ROLES:
			raise PermissionDenied('Only the staff member handling this ticket can forward it.')
		destination = request.data.get('destination')
		if destination not in dict(OutpatientTicket.DESTINATION_CHOICES):
			raise ValidationError({'destination': 'Choose a valid destination.'})
		assigned_to = None
		if request.data.get('assignedTo') not in (None, ''):
			assigned_to = User.objects.filter(id=request.data['assignedTo'], facility_id=ticket.facility_id, is_active=True).first()
			if assigned_to is None:
				raise ValidationError({'assignedTo': 'The assigned user must belong to this facility.'})
		notes = request.data.get('notes', '')
		OutpatientTicketMovement.objects.create(
			ticket=ticket, from_destination=ticket.destination, to_destination=destination,
			forwarded_by=request.user, assigned_to=assigned_to, notes=notes,
		)
		ticket.destination = destination
		ticket.assigned_to = assigned_to
		ticket.status = 'waiting'
		ticket.called_by = None
		if notes:
			ticket.notes = notes
		ticket.save(update_fields=['destination', 'assigned_to', 'status', 'called_by', 'notes', 'updated_at'])
		return Response(self.get_serializer(ticket).data)

	@action(detail=True, methods=['post'])
	def complete(self, request, pk=None):
		ticket = self.get_object()
		if ticket.status != 'called':
			raise ValidationError({'status': 'Call the ticket before completing it.'})
		if ticket.called_by_id != request.user.id and request.user.role not in self.PRIVILEGED_ROLES:
			raise PermissionDenied('Only the staff member handling this ticket can complete it.')
		ticket.status = 'completed'
		ticket.completed_at = timezone.now()
		ticket.save(update_fields=['status', 'completed_at', 'updated_at'])
		return Response(self.get_serializer(ticket).data)


class EhrRecordViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'ehr'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY, request=request)
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
		ehr = serializer.save(facility_id=facility_id, patient=patient, doctor=doctor_name)
		# DHA: write provenance log if a coded concept was stored
		if ehr.diagnosis_code:
			log_concept_provenance(
				user=user,
				facility=ehr.facility,
				record_type='ehr',
				record_id=str(ehr.id),
				concept={
					'code_system': ehr.diagnosis_system,
					'code': ehr.diagnosis_code,
					'display': ehr.diagnosis_text or ehr.diagnosis,
				},
			)
			AuditLog.objects.create(
				facility=ehr.facility,
				user=user,
				action='create',
				model_name='EhrRecord',
				object_id=str(ehr.id),
				description=(
					f'EHR record created for patient {ehr.patient.patient_id} by {doctor_name}. '
					f'Coded diagnosis: [{ehr.diagnosis_system}:{ehr.diagnosis_code}] '
					f'{ehr.diagnosis_text or ehr.diagnosis}'
				),
				ip_address=self.request.META.get('REMOTE_ADDR'),
			)

	def perform_update(self, serializer):
		record = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		if record.facility_id != facility_id:
			raise PermissionDenied('You cannot modify EHR records from another facility.')
		ehr = serializer.save()
		# DHA: write provenance log if coded concept was updated
		if ehr.diagnosis_code:
			log_concept_provenance(
				user=self.request.user,
				facility=ehr.facility,
				record_type='ehr',
				record_id=str(ehr.id),
				concept={
					'code_system': ehr.diagnosis_system,
					'code': ehr.diagnosis_code,
					'display': ehr.diagnosis_text or ehr.diagnosis,
				},
			)
			AuditLog.objects.create(
				facility=ehr.facility,
				user=self.request.user,
				action='update',
				model_name='EhrRecord',
				object_id=str(ehr.id),
				description=(
					f'EHR record updated for patient {ehr.patient.patient_id}. '
					f'Coded diagnosis: [{ehr.diagnosis_system}:{ehr.diagnosis_code}] '
					f'{ehr.diagnosis_text or ehr.diagnosis}'
				),
				ip_address=self.request.META.get('REMOTE_ADDR'),
			)

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
		visit = serializer.save(facility_id=facility_id, patient=patient)
		
		if visit.diagnosis_code:
			log_concept_provenance(
				user=self.request.user,
				facility=visit.facility,
				record_type='visit',
				record_id=str(visit.id),
				concept={
					'code_system': visit.diagnosis_system,
					'code': visit.diagnosis_code,
					'display': visit.diagnosis_text or visit.diagnosis,
				},
			)
			AuditLog.objects.create(
				facility=visit.facility,
				user=self.request.user,
				action='create',
				model_name='PatientVisit',
				object_id=str(visit.id),
				description=(
					f'Visit record created for patient {visit.patient.patient_id}. '
					f'Coded diagnosis: [{visit.diagnosis_system}:{visit.diagnosis_code}] '
					f'{visit.diagnosis_text or visit.diagnosis}'
				),
				ip_address=self.request.META.get('REMOTE_ADDR'),
			)

		headers = self.get_success_headers(serializer.data)

		return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class _FacilityPatientScopedViewSet(viewsets.ModelViewSet):
	"""Shared facilityId/patientId query-param scoping for EHR sub-records."""

	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'ehr'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	ordering = ['-created_at']

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY, request=request)

	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')
		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_facility_id_from_query(self):
		facility_id = self.request.query_params.get('facilityId') or self.request.query_params.get('facility_id')
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId query param is required.'})
		return self._parse_facility_id(facility_id, 'facilityId must be a valid integer.')

	def _get_facility_id_from_body(self):
		facility_id = self.request.data.get('facilityId') or self.request.data.get('facility_id')
		if facility_id is None:
			raise ValidationError({'facilityId': 'facilityId is required in request body.'})
		return self._parse_facility_id(facility_id, 'facilityId must be a valid integer.')

	def _enforce_user_facility_access(self, facility_id):
		user = self.request.user
		if user.facility_id and user.facility_id != facility_id:
			raise PermissionDenied('You cannot access records from another facility.')
		if not user.facility_id and user.role != 'admin':
			raise PermissionDenied('Your account is not assigned to a facility.')

	def get_queryset(self):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		queryset = self.model_class.objects.filter(facility_id=facility_id, is_active=True)
		patient_id = self.request.query_params.get('patientId')
		if patient_id:
			queryset = queryset.filter(patient__patient_id=patient_id)
		return queryset

	def perform_create(self, serializer):
		facility_id = self._get_facility_id_from_body()
		self._enforce_user_facility_access(facility_id)
		serializer.save(facility_id=facility_id)

	def perform_update(self, serializer):
		record = self.get_object()
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		if record.facility_id != facility_id:
			raise PermissionDenied('You cannot modify records from another facility.')
		serializer.save()

	def perform_destroy(self, instance):
		facility_id = self._get_facility_id_from_query()
		self._enforce_user_facility_access(facility_id)
		if instance.facility_id != facility_id:
			raise PermissionDenied('You cannot delete records from another facility.')
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


class ProblemItemViewSet(_FacilityPatientScopedViewSet):
	model_class = ProblemItem
	serializer_class = ProblemItemSerializer
	search_fields = ['display', 'code', 'notes']


class AllergyItemViewSet(_FacilityPatientScopedViewSet):
	model_class = AllergyItem
	serializer_class = AllergyItemSerializer
	search_fields = ['allergen_name', 'reaction']


class CpoeOrderViewSet(_FacilityPatientScopedViewSet):
	model_class = CpoeOrder
	serializer_class = CpoeOrderSerializer
	search_fields = ['title', 'order_type', 'instructions']
