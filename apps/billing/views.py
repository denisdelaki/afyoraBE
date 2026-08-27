# billing/views.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.db.models import Q
from core.models import Facility
from core.utils import check_module_permission
from patients.models import Patient
from .models import Invoice, Payment
from .serializers import InvoiceSerializer, PaymentSerializer, RecordPaymentSerializer


def parse_facility_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip('/')
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_patient_from_request(request):
    """Shared helper: resolves patient and facility_id from query params."""
    patient_param = (
        request.query_params.get('patientId')
        or request.query_params.get('patient_id')
        or request.query_params.get('patient')
    )
    facility_val = (
        request.query_params.get('facilityId')
        or request.query_params.get('facility_id')
    )
    facility_id = parse_facility_id(facility_val)
    return patient_param, facility_id


def _lookup_patient(patient_param, facility_id):
    """Shared helper: returns (patient, error_response) given raw patientId string."""
    clean_pat = str(patient_param).strip().rstrip('/')
    qs = Patient.objects.filter(
        Q(patient_id__iexact=clean_pat)
        | (Q(id=int(clean_pat)) if clean_pat.isdigit() else Q())
    )
    if facility_id:
        qs = qs.filter(facility_id=facility_id)
    patient = qs.first()
    if not patient:
        # fallback without facility filter
        patient = Patient.objects.filter(
            Q(patient_id__iexact=clean_pat)
            | (Q(id=int(clean_pat)) if clean_pat.isdigit() else Q())
        ).first()
    return patient


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    CRUD API for facility Invoices:
    GET    /api/billing/invoices/?facilityId=9/
    POST   /api/billing/invoices/?facilityId=9/
    GET    /api/billing/invoices/{id}/?facilityId=9/
    PUT    /api/billing/invoices/{id}/?facilityId=9/
    DELETE /api/billing/invoices/{id}/?facilityId=9/
    POST   /api/billing/invoices/{id}/payments?facilityId=9/
    """
    permission_classes = [IsAuthenticated]
    queryset = Invoice.objects.select_related('patient', 'facility').prefetch_related('items', 'insurance')
    serializer_class = InvoiceSerializer
    lookup_field = 'id'

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user and request.user.is_authenticated:
            check_module_permission(request.user, 'billing')

    def get_facility_id(self):
        facility_val = (
            self.request.query_params.get('facilityId')
            or self.request.query_params.get('facility_id')
            or self.request.data.get('facilityId')
            or self.request.data.get('facility_id')
        )
        parsed = parse_facility_id(facility_val)
        if parsed is not None:
            return parsed

        if getattr(self.request.user, 'facility_id', None):
            return self.request.user.facility_id

        return None

    def get_queryset(self):
        qs = super().get_queryset()
        facility_id = self.get_facility_id()
        if facility_id:
            qs = qs.filter(facility_id=facility_id)

        patient_param = self.request.query_params.get('patientId') or self.request.query_params.get('patient')
        if patient_param:
            clean_pat = str(patient_param).strip().rstrip('/')
            if clean_pat.isdigit():
                qs = qs.filter(Q(patient__id=int(clean_pat)) | Q(patient__patient_id__iexact=clean_pat))
            else:
                qs = qs.filter(patient__patient_id__iexact=clean_pat)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        items = serializer.data
        return Response({
            'success': True,
            'data': {
                'items': items,
                'total': len(items),
                'page': 1,
                'pageSize': len(items) or 20
            }
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        out_serializer = self.get_serializer(invoice)
        return Response({
            'success': True,
            'message': 'Invoice created successfully',
            'data': out_serializer.data
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response({
            'success': True,
            'message': 'Invoice updated successfully',
            'data': self.get_serializer(invoice).data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({
            'success': True,
            'message': 'Invoice deleted successfully'
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='payments')
    def record_payment(self, request, id=None):
        invoice = self.get_object()
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = Payment.objects.create(
            invoice=invoice,
            amount=serializer.validated_data['amount'],
            method=serializer.validated_data['method'],
            status='Completed',
        )
        invoice.payment_method = payment.method
        invoice.save(update_fields=['payment_method'])
        invoice.recalc_status()

        return Response({
            'success': True,
            'message': 'Payment recorded successfully',
            'data': PaymentSerializer(payment).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='pharmacy-charges')
    def pharmacy_charges(self, request):
        """
        GET /api/billing/invoices/pharmacy-charges/?patientId=PAT0001&facilityId=9/
        """
        return PatientPharmacyChargesView().get(request)

    @action(detail=False, methods=['get'], url_path='lab-charges')
    def lab_charges(self, request):
        """
        GET /api/billing/invoices/lab-charges/?patientId=PAT0001&facilityId=9/
        """
        return PatientLabChargesView().get(request)

    @action(detail=False, methods=['get'], url_path='radiology-charges')
    def radiology_charges(self, request):
        """
        GET /api/billing/invoices/radiology-charges/?patientId=PAT0001&facilityId=9/
        """
        return PatientRadiologyChargesView().get(request)


class PatientPharmacyChargesView(APIView):
    """
    GET /api/billing/patient-pharmacy-charges/?patientId=PAT0001&facilityId=9/
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .utils import get_patient_pharmacy_charges
        patient_param, facility_id = _resolve_patient_from_request(request)
        if not patient_param:
            return Response({'success': False, 'error': 'patientId query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = _lookup_patient(patient_param, facility_id)
        if not patient:
            return Response({'success': False, 'error': f"Patient '{patient_param}' not found."}, status=status.HTTP_404_NOT_FOUND)

        total_amount, items = get_patient_pharmacy_charges(patient, facility_id=facility_id)
        return Response({
            'success': True,
            'data': {
                'patientId': patient.patient_id,
                'patientName': f"{patient.first_name} {patient.last_name}".strip(),
                'facilityId': facility_id or patient.facility_id,
                'totalAmount': total_amount,
                'items': items
            }
        }, status=status.HTTP_200_OK)


class PatientLabChargesView(APIView):
    """
    GET /api/billing/patient-lab-charges/?patientId=PAT0001&facilityId=9/
    Returns itemized lab/test charges for a patient to pre-populate billing services.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .utils import get_patient_lab_charges
        patient_param, facility_id = _resolve_patient_from_request(request)
        if not patient_param:
            return Response({'success': False, 'error': 'patientId query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = _lookup_patient(patient_param, facility_id)
        if not patient:
            return Response({'success': False, 'error': f"Patient '{patient_param}' not found."}, status=status.HTTP_404_NOT_FOUND)

        total_amount, items = get_patient_lab_charges(patient, facility_id=facility_id)
        return Response({
            'success': True,
            'data': {
                'patientId': patient.patient_id,
                'patientName': f"{patient.first_name} {patient.last_name}".strip(),
                'facilityId': facility_id or patient.facility_id,
                'totalAmount': total_amount,
                'items': items
            }
        }, status=status.HTTP_200_OK)


class PatientRadiologyChargesView(APIView):
    """
    GET /api/billing/patient-radiology-charges/?patientId=PAT0001&facilityId=9/
    Returns itemized radiology/imaging charges for a patient to pre-populate billing services.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .utils import get_patient_radiology_charges
        patient_param, facility_id = _resolve_patient_from_request(request)
        if not patient_param:
            return Response({'success': False, 'error': 'patientId query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        patient = _lookup_patient(patient_param, facility_id)
        if not patient:
            return Response({'success': False, 'error': f"Patient '{patient_param}' not found."}, status=status.HTTP_404_NOT_FOUND)

        total_amount, items = get_patient_radiology_charges(patient, facility_id=facility_id)
        return Response({
            'success': True,
            'data': {
                'patientId': patient.patient_id,
                'patientName': f"{patient.first_name} {patient.last_name}".strip(),
                'facilityId': facility_id or patient.facility_id,
                'totalAmount': total_amount,
                'items': items
            }
        }, status=status.HTTP_200_OK)


class PaymentViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = Payment.objects.select_related('invoice', 'invoice__patient', 'invoice__facility')
    serializer_class = PaymentSerializer

    def get_facility_id(self):
        facility_val = (
            self.request.query_params.get('facilityId')
            or self.request.query_params.get('facility_id')
        )
        parsed = parse_facility_id(facility_val)
        if parsed is not None:
            return parsed
        if getattr(self.request.user, 'facility_id', None):
            return self.request.user.facility_id
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        facility_id = self.get_facility_id()
        if facility_id:
            qs = qs.filter(invoice__facility_id=facility_id)
        return qs.order_by('-date', '-id')

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(qs, many=True)
        items = serializer.data
        return Response({
            'success': True,
            'data': {
                'items': items,
                'total': len(items),
                'page': 1,
                'pageSize': len(items) or 20
            }
        }, status=status.HTTP_200_OK)