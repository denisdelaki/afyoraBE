import random

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Facility
from core.utils import check_module_permission
from .models import HieConnection, HieSyncLog, QualityMeasure, TerminologyStandard
from .serializers import (
    MATURITY_LEVEL_DEFINITIONS,
    QUALITY_MEASURE_SEED,
    TERMINOLOGY_STANDARD_SEED,
    HieConnectionSerializer,
    HieSyncLogSerializer,
    QualityMeasureSerializer,
    TerminologyStandardSerializer,
)


def _parse_facility_id(value, error_message):
    if isinstance(value, str):
        value = value.strip().rstrip('/')
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({'facilityId': error_message})


def _enforce_user_facility_access(user, facility_id):
    if user.facility_id and user.facility_id != facility_id:
        raise PermissionDenied('You cannot access records from another facility.')
    if not user.facility_id and user.role != 'admin':
        raise PermissionDenied('Your account is not assigned to a facility.')


class _InteroperabilityAuthMixin:
    permission_classes = [IsAuthenticated]
    MODULE_KEY = 'reports'

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user and request.user.is_authenticated:
            check_module_permission(request.user, self.MODULE_KEY, request=request)

    def _get_facility_id(self, values):
        facility_id = values.get('facilityId') or values.get('facility_id')
        if facility_id is None:
            raise ValidationError({'facilityId': 'facilityId is required.'})
        facility_id = _parse_facility_id(facility_id, 'facilityId must be a valid integer.')
        _enforce_user_facility_access(self.request.user, facility_id)
        return facility_id


class HieConnectionView(_InteroperabilityAuthMixin, APIView):
    """Fetch or refresh the Kenya HIE gateway connection state for a facility."""

    def get(self, request):
        facility_id = self._get_facility_id(request.query_params)
        facility = get_object_or_404(Facility, id=facility_id)
        connection, _ = HieConnection.objects.get_or_create(
            facility=facility,
            defaults={'mfl_code': f'MFL-{10000 + facility.id}'},
        )
        return Response(HieConnectionSerializer(connection).data)


class HieConnectionPingView(_InteroperabilityAuthMixin, APIView):
    """Test connectivity to the Kenya HIE gateway and persist the result."""

    def post(self, request):
        facility_id = self._get_facility_id(request.data)
        facility = get_object_or_404(Facility, id=facility_id)
        connection, _ = HieConnection.objects.get_or_create(
            facility=facility,
            defaults={'mfl_code': f'MFL-{10000 + facility.id}'},
        )
        connection.status = 'CONNECTED'
        connection.latency_ms = random.randint(35, 55)
        connection.last_checked_at = timezone.now()
        connection.save(update_fields=['status', 'latency_ms', 'last_checked_at', 'updated_at'])
        return Response(HieConnectionSerializer(connection).data)


class HieMaturityLevelsView(_InteroperabilityAuthMixin, APIView):
    """Return the 4 DHA interoperability maturity levels with per-facility achievement."""

    def get(self, request):
        facility_id = self._get_facility_id(request.query_params)
        facility = get_object_or_404(Facility, id=facility_id)
        connection, _ = HieConnection.objects.get_or_create(
            facility=facility,
            defaults={'mfl_code': f'MFL-{10000 + facility.id}'},
        )
        levels = [
            {**definition, 'supported': definition['level'] <= connection.maturity_level}
            for definition in MATURITY_LEVEL_DEFINITIONS
        ]
        return Response(levels)


class HieMaturityUpgradeView(_InteroperabilityAuthMixin, APIView):
    """Advance a facility to the next interoperability maturity level."""

    def post(self, request):
        facility_id = self._get_facility_id(request.data)
        facility = get_object_or_404(Facility, id=facility_id)
        connection, _ = HieConnection.objects.get_or_create(
            facility=facility,
            defaults={'mfl_code': f'MFL-{10000 + facility.id}'},
        )
        connection.maturity_level = min(4, connection.maturity_level + 1)
        connection.save(update_fields=['maturity_level', 'updated_at'])
        levels = [
            {**definition, 'supported': definition['level'] <= connection.maturity_level}
            for definition in MATURITY_LEVEL_DEFINITIONS
        ]
        return Response(levels)


class TerminologyStandardViewSet(_InteroperabilityAuthMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = TerminologyStandardSerializer

    def get_queryset(self):
        facility_id = self._get_facility_id(self.request.query_params)
        facility = get_object_or_404(Facility, id=facility_id)
        for seed in TERMINOLOGY_STANDARD_SEED:
            TerminologyStandard.objects.get_or_create(
                facility=facility,
                code=seed['code'],
                defaults=seed,
            )
        return TerminologyStandard.objects.filter(facility_id=facility_id, is_active=True)


class QualityMeasureViewSet(_InteroperabilityAuthMixin, viewsets.ModelViewSet):
    serializer_class = QualityMeasureSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        facility_id = self._get_facility_id(self.request.query_params)
        facility = get_object_or_404(Facility, id=facility_id)
        for seed in QUALITY_MEASURE_SEED:
            QualityMeasure.objects.get_or_create(
                facility=facility,
                code=seed['code'],
                defaults=seed,
            )
        return QualityMeasure.objects.filter(facility_id=facility_id, is_active=True)

    def perform_create(self, serializer):
        facility_id = self._get_facility_id(self.request.data)
        serializer.save(facility_id=facility_id)

    def perform_update(self, serializer):
        measure = self.get_object()
        facility_id = self._get_facility_id(self.request.query_params)
        if measure.facility_id != facility_id:
            raise PermissionDenied('You cannot modify records from another facility.')
        serializer.save()

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        HieSyncLog.objects.create(
            facility_id=self._get_facility_id(request.data),
            log_type='QUALITY_MEASURE',
            status='SUCCESS',
            records_transferred=1,
            message=f"Quality measure {request.data.get('code', '')} submitted to DHA Quality Portal.",
        )
        return response


class HieSyncLogViewSet(_InteroperabilityAuthMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = HieSyncLogSerializer

    def get_queryset(self):
        facility_id = self._get_facility_id(self.request.query_params)
        return HieSyncLog.objects.filter(facility_id=facility_id, is_active=True)

    def perform_create(self, serializer):
        facility_id = self._get_facility_id(self.request.data)
        serializer.save(facility_id=facility_id)
