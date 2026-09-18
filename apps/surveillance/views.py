from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils import check_module_permission
from .models import IdsrWeeklyReport, NotifiableDiseaseAlert, PublicHealthEvent
from .serializers import IdsrWeeklyReportSerializer, NotifiableDiseaseAlertSerializer, PublicHealthEventSerializer


class _FacilityScopedSurveillanceViewSet(viewsets.ModelViewSet):
    """Shared facilityId scoping for surveillance & MOH reporting records."""

    permission_classes = [IsAuthenticated]
    MODULE_KEY = 'reports'
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

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
        return self.model_class.objects.filter(facility_id=facility_id, is_active=True)

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


class NotifiableDiseaseAlertViewSet(_FacilityScopedSurveillanceViewSet):
    model_class = NotifiableDiseaseAlert
    serializer_class = NotifiableDiseaseAlertSerializer
    search_fields = ['disease_name', 'patient_name', 'sub_county']

    @action(detail=True, methods=['post'], url_path='notify-moh')
    def notify_moh(self, request, pk=None):
        """Mark disease alert as notified to MOH in real-time."""
        alert = self.get_object()
        alert.moh_notified = True
        alert.moh_notified_at = timezone.now()
        alert.status = 'REPORTED' if alert.status == 'TRIGGERED' else alert.status
        alert.save(update_fields=['moh_notified', 'moh_notified_at', 'status', 'updated_at'])
        return Response(self.get_serializer(alert).data)

    @action(detail=False, methods=['get'], url_path='compliance-summary')
    def compliance_summary(self, request):
        """Return a public health surveillance compliance summary."""
        facility_id = self._get_facility_id_from_query()
        self._enforce_user_facility_access(facility_id)

        total_alerts = NotifiableDiseaseAlert.objects.filter(facility_id=facility_id, is_active=True).count()
        moh_notified = NotifiableDiseaseAlert.objects.filter(facility_id=facility_id, is_active=True, moh_notified=True).count()
        idsr_reports = IdsrWeeklyReport.objects.filter(facility_id=facility_id, is_active=True).count()
        submitted_idsr = IdsrWeeklyReport.objects.filter(facility_id=facility_id, is_active=True, status='SUBMITTED').count()

        immediate_score = (moh_notified / total_alerts * 100) if total_alerts else 100.0
        idsr_score = (submitted_idsr / idsr_reports * 100) if idsr_reports else 100.0
        overall_score = round((immediate_score + idsr_score) / 2, 1)

        return Response({
            'overallScore': overall_score,
            'status': 'Compliant' if overall_score >= 80 else 'Action Required',
            'lastAudited': timezone.now().date().isoformat(),
            'metrics': [
                {
                    'id': 'REP-01',
                    'category': 'Surveillance Reporting',
                    'name': 'Immediate Reportable Diseases Real-Time Alert System',
                    'status': 'Compliant' if immediate_score >= 80 else 'Partial',
                    'scorePercentage': round(immediate_score, 1),
                    'weight': 50,
                    'notes': f'{moh_notified}/{total_alerts} alerts notified to MOH.',
                },
                {
                    'id': 'REP-02',
                    'category': 'Surveillance Reporting',
                    'name': 'IDSR 504 Weekly Reporting & Aggregation',
                    'status': 'Compliant' if idsr_score >= 80 else 'Partial',
                    'scorePercentage': round(idsr_score, 1),
                    'weight': 50,
                    'notes': f'{submitted_idsr}/{idsr_reports} weekly reports submitted to KHIS.',
                },
            ],
        })


class IdsrWeeklyReportViewSet(_FacilityScopedSurveillanceViewSet):
    model_class = IdsrWeeklyReport
    serializer_class = IdsrWeeklyReportSerializer
    search_fields = ['sub_county', 'county']

    def list(self, request, *args, **kwargs):
        epi_week = request.query_params.get('epiWeek')
        year = request.query_params.get('year')
        if epi_week and year:
            queryset = self.get_queryset().filter(epi_week=epi_week, year=year)
            report = queryset.first()
            if report is None:
                return Response({'detail': 'No IDSR report found for the requested week.'}, status=status.HTTP_404_NOT_FOUND)
            return Response(self.get_serializer(report).data)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='submit-khis')
    def submit_to_khis(self, request, pk=None):
        """Mark report as submitted to KHIS/DHIS2."""
        import uuid

        report = self.get_object()
        report.status = 'SUBMITTED'
        report.submission_date = timezone.now()
        report.submitted_by = request.data.get('submittedBy', 'System')
        report.khis_submission_id = f"KHIS-{uuid.uuid4().hex[:12].upper()}"
        report.save(update_fields=['status', 'submission_date', 'submitted_by', 'khis_submission_id', 'updated_at'])
        return Response(self.get_serializer(report).data)


class PublicHealthEventViewSet(_FacilityScopedSurveillanceViewSet):
    model_class = PublicHealthEvent
    serializer_class = PublicHealthEventSerializer
    search_fields = ['event_name', 'location']
