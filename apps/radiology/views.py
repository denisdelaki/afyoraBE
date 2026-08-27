from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Facility
from core.utils import check_module_permission
from .models import ImagingRequest, ImagingReport, ImagingStudy, ImagingImage
from .serializers import ImagingRequestSerializer, ImagingReportSerializer, ImagingStudySerializer, ImagingImageSerializer


class FacilityScopedRadiologyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    MODULE_KEY = 'radiology'

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
                raise PermissionDenied('You cannot access radiology data from another facility.')
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


class ImagingStudyViewSet(FacilityScopedRadiologyViewSet):
    serializer_class = ImagingStudySerializer
    lookup_field = 'study_id'
    lookup_url_kwarg = 'study_id'
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    filterset_fields = ['category']
    search_fields = ['study_id', 'name', 'category']
    ordering = ['name', '-created_at']

    def get_queryset(self):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        return ImagingStudy.objects.filter(facility=facility, is_active=True)

    def perform_create(self, serializer):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        serializer.save(facility=facility)

    def perform_update(self, serializer):
        study = self.get_object()
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        if study.facility_id != facility.id:
            raise PermissionDenied('You cannot modify studies from another facility.')
        serializer.save()

    def perform_destroy(self, instance):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        if instance.facility_id != facility.id:
            raise PermissionDenied('You cannot delete studies from another facility.')
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


class ImagingRequestViewSet(FacilityScopedRadiologyViewSet):
    serializer_class = ImagingRequestSerializer
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

        queryset = ImagingRequest.objects.filter(facility=facility, is_active=True).select_related('study')

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

        # Soft-delete any associated report
        report = ImagingReport.objects.filter(
            facility_id=facility.id,
            request=instance,
            is_active=True,
        ).first()
        if report is not None:
            report.is_active = False
            report.save(update_fields=['is_active', 'updated_at'])

    @action(detail=True, methods=['post', 'patch', 'put'])
    def status(self, request, request_id=None):
        request_obj = self.get_object()
        new_status = request.data.get('status')
        if new_status:
            valid_statuses = [choice[0] for choice in ImagingRequest.STATUS_CHOICES]
            if new_status not in valid_statuses:
                raise ValidationError({'status': f'Invalid status. Allowed: {", ".join(valid_statuses)}'})
            request_obj.status = new_status
            request_obj.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(request_obj).data, status=200)

    @action(detail=True, methods=['post', 'patch'])
    def schedule(self, request, request_id=None):
        request_obj = self.get_object()
        request_obj.status = 'In Progress'
        request_obj.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(request_obj).data, status=200)


class ImagingReportViewSet(FacilityScopedRadiologyViewSet):
    serializer_class = ImagingReportSerializer
    lookup_field = 'report_id'
    lookup_url_kwarg = 'report_id'
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
    filterset_fields = ['status']
    search_fields = ['report_id', 'request__patient', 'request__patient_id', 'radiologist']
    ordering = ['-scan_date', '-created_at']

    def get_queryset(self):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})

        queryset = ImagingReport.objects.filter(
            facility=facility, is_active=True,
        ).select_related('request', 'request__study')

        order_id = self.request.query_params.get('orderId')
        if order_id:
            queryset = queryset.filter(request__request_id=order_id)

        return queryset

    def perform_create(self, serializer):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        serializer.save(facility=facility)

    def perform_update(self, serializer):
        report = self.get_object()
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        if report.facility_id != facility.id:
            raise PermissionDenied('You cannot modify reports from another facility.')
        serializer.save()

    def perform_destroy(self, instance):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        if instance.facility_id != facility.id:
            raise PermissionDenied('You cannot delete reports from another facility.')
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


class ImagingImageViewSet(FacilityScopedRadiologyViewSet):
    serializer_class = ImagingImageSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})

        queryset = ImagingImage.objects.filter(facility=facility, is_active=True).select_related('request')

        order_id = self.request.query_params.get('orderId')
        if order_id:
            queryset = queryset.filter(request__request_id=order_id)

        return queryset

    def perform_create(self, serializer):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        serializer.save(facility=facility)

    def perform_destroy(self, instance):
        facility = self._get_target_facility()
        if facility is None:
            raise ValidationError({'facilityId': 'Facility not found.'})
        if instance.facility_id != facility.id:
            raise PermissionDenied('You cannot delete images from another facility.')
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
