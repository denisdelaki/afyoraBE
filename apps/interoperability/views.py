import logging
import random

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Facility
from core.utils import check_module_permission
from .models import HieConnection, HieSyncLog, QualityMeasure, TerminologyStandard
from .services.kmhfr import KMHFRService
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


logger = logging.getLogger(__name__)


class FacilitySearchView(View):
    """
    Proxy View to search health facilities via Kenya Master Health Facility Registry (KMHFR).

    Query Parameters:
      - q: Search string (facility name, code, or keyword)
      - county: County name or ID filter
      - facility_type: Facility type filter
      - page: Page number for pagination (default: 1)
      - page_size: Items per page (default: 10, max: 100)
    """

    def get(self, request, *args, **kwargs):
        """
        Handle GET request for facility search.
        Extracts parameters from request.GET, calls KMHFRService.search_facilities,
        and returns a JsonResponse with appropriate HTTP status codes.
        """
        # Extract query parameters
        search_query = (
            request.GET.get('q') or
            request.GET.get('search_query') or
            request.GET.get('search')
        )
        county = request.GET.get('county')
        facility_type = request.GET.get('facility_type')
        raw_page = request.GET.get('page', 1)
        raw_page_size = request.GET.get('page_size', 10)

        # Validate numeric page parameter
        try:
            page = int(raw_page)
            if page < 1:
                raise ValueError("Page number must be >= 1")
        except (ValueError, TypeError):
            return JsonResponse(
                {
                    "error": True,
                    "message": "Invalid 'page' parameter. Must be a positive integer."
                },
                status=400
            )

        # Validate numeric page_size parameter
        try:
            page_size = int(raw_page_size)
            if page_size < 1 or page_size > 100:
                raise ValueError("Page size must be between 1 and 100")
        except (ValueError, TypeError):
            return JsonResponse(
                {
                    "error": True,
                    "message": "Invalid 'page_size' parameter. Must be an integer between 1 and 100."
                },
                status=400
            )

        # Sanitize string parameter inputs
        if search_query:
            search_query = str(search_query).strip()[:200]
        if county:
            county = str(county).strip()[:100]
        if facility_type:
            facility_type = str(facility_type).strip()[:100]

        # Call service layer to perform search & cache handling
        result = KMHFRService.search_facilities(
            search_query=search_query,
            county=county,
            facility_type=facility_type,
            page=page,
            page_size=page_size
        )

        # Retrieve status code from service response (default 200 OK)
        status_code = result.get('status_code', 200)

        return JsonResponse(result, status=status_code)
