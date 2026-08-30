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


class MpesaConfigView(APIView):
    """
    GET /api/billing/mpesa-config/?facilityId=1
    POST /api/billing/mpesa-config/?facilityId=1
    """
    permission_classes = [AllowAny]

    def _get_facility(self, request):
        facility_val = (
            request.query_params.get('facilityId')
            or request.query_params.get('facility_id')
            or request.data.get('facilityId')
            or request.data.get('facility_id')
        )
        parsed = parse_facility_id(facility_val)
        if parsed:
            return Facility.objects.filter(id=parsed).first()
        if request.user and getattr(request.user, 'facility_id', None):
            return Facility.objects.filter(id=request.user.facility_id).first()
        return Facility.objects.first()

    def get(self, request):
        from .models import MpesaConfig
        from .serializers import MpesaConfigSerializer
        from .mpesa_service import get_facility_mpesa_config

        facility = self._get_facility(request)
        if not facility:
            return Response({'success': False, 'error': 'Facility not found'}, status=status.HTTP_404_NOT_FOUND)

        config = get_facility_mpesa_config(facility)
        serializer = MpesaConfigSerializer(config)
        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        from .models import MpesaConfig
        from .serializers import MpesaConfigSerializer
        from .mpesa_service import get_facility_mpesa_config

        facility = self._get_facility(request)
        if not facility:
            return Response({'success': False, 'error': 'Facility not found'}, status=status.HTTP_404_NOT_FOUND)

        config = get_facility_mpesa_config(facility)
        serializer = MpesaConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'success': True,
            'message': 'M-Pesa configuration updated successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def put(self, request):
        return self.post(request)


class MpesaSTKPushView(APIView):
    """
    POST /api/billing/mpesa/stk-push/?facilityId=1
    Payload: { "invoiceId": "INV0001", "phoneNumber": "0712345678", "amount": 500 }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from .models import Invoice, MpesaTransaction
        from .serializers import MpesaSTKPushRequestSerializer, MpesaTransactionSerializer
        from .mpesa_service import get_facility_mpesa_config, send_stk_push, format_phone_number

        serializer = MpesaSTKPushRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invoice_id = serializer.validated_data['invoiceId']
        phone_number = serializer.validated_data['phoneNumber']

        invoice = Invoice.objects.filter(id=invoice_id).first()
        if not invoice:
            return Response({'success': False, 'error': f"Invoice '{invoice_id}' not found."}, status=status.HTTP_404_NOT_FOUND)

        amount = serializer.validated_data.get('amount') or invoice.total
        if float(amount) <= 0:
            return Response({'success': False, 'error': 'Invoice amount must be greater than 0.'}, status=status.HTTP_400_BAD_REQUEST)

        facility = invoice.facility
        if not facility:
            facility_val = request.query_params.get('facilityId') or request.data.get('facilityId')
            parsed = parse_facility_id(facility_val)
            if parsed:
                facility = Facility.objects.filter(id=parsed).first()

        config = get_facility_mpesa_config(facility)

        # Build callback URL
        callback_url = request.build_absolute_uri('/api/billing/mpesa/callback/')
        if 'localhost' in callback_url or '127.0.0.1' in callback_url:
            # Fallback URL format for local dev callback placeholder
            callback_url = "https://afyorahms.com/api/billing/mpesa/callback/"

        account_ref = f"{config.account_reference_prefix or 'Afyora'}-{invoice.id}"

        res = send_stk_push(
            config=config,
            phone_number=phone_number,
            amount=float(amount),
            account_ref=account_ref,
            callback_url=callback_url
        )

        if res.get('success'):
            checkout_req_id = res['checkout_request_id']
            merchant_req_id = res['merchant_request_id']

            txn = MpesaTransaction.objects.create(
                invoice=invoice,
                facility=facility,
                phone_number=format_phone_number(phone_number),
                amount=amount,
                checkout_request_id=checkout_req_id,
                merchant_request_id=merchant_req_id,
                status='Pending'
            )

            return Response({
                'success': True,
                'message': res.get('customer_message') or 'STK Push sent to patient phone.',
                'data': {
                    'checkoutRequestId': checkout_req_id,
                    'merchantRequestId': merchant_req_id,
                    'transaction': MpesaTransactionSerializer(txn).data
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': res.get('error') or 'Failed to trigger M-Pesa STK Push.'
            }, status=status.HTTP_400_BAD_REQUEST)


class MpesaCallbackView(APIView):
    """
    POST /api/billing/mpesa/callback/
    Webhook endpoint for Safaricom Daraja STK Push result callbacks.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from .models import MpesaTransaction, Payment
        from django.utils import timezone
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"M-Pesa Callback Payload Received: {request.data}")

        try:
            body = request.data.get('Body', {}).get('stkCallback', {})
            checkout_req_id = body.get('CheckoutRequestID')
            result_code = body.get('ResultCode')
            result_desc = body.get('ResultDesc', '')

            if not checkout_req_id:
                return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})

            txn = MpesaTransaction.objects.filter(checkout_request_id=checkout_req_id).first()
            if not txn:
                logger.warning(f"M-Pesa Callback: Transaction '{checkout_req_id}' not found.")
                return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'})

            txn.result_code = result_code
            txn.result_desc = result_desc

            if result_code == 0:
                txn.status = 'Completed'
                meta_items = body.get('CallbackMetadata', {}).get('Item', [])
                receipt = ""
                for item in meta_items:
                    if item.get('Name') == 'MpesaReceiptNumber':
                        receipt = item.get('Value', '')
                        txn.mpesa_receipt_number = receipt

                txn.transaction_date = timezone.now()
                txn.save()

                if txn.invoice:
                    # Automatically create completed Payment for Invoice
                    invoice = txn.invoice
                    payment_exists = Payment.objects.filter(
                        invoice=invoice, amount=txn.amount, method='M-Pesa'
                    ).exists()

                    if not payment_exists:
                        Payment.objects.create(
                            invoice=invoice,
                            amount=txn.amount,
                            method='M-Pesa',
                            status='Completed'
                        )
                        invoice.payment_method = 'M-Pesa'
                        invoice.save(update_fields=['payment_method'])
                        invoice.recalc_status()
                elif txn.subscription_payment:
                    from .mpesa_service import complete_subscription_payment
                    complete_subscription_payment(txn.subscription_payment, receipt)
            else:
                txn.status = 'Cancelled' if result_code == 1032 else 'Failed'
                txn.save()
                if txn.subscription_payment:
                    txn.subscription_payment.status = 'failed'
                    txn.subscription_payment.notes = f"Payment failed: {result_desc}"
                    txn.subscription_payment.save()

        except Exception as e:
            logger.error(f"Error handling M-Pesa Callback: {e}")

        # Always respond to Safaricom with 200 OK
        return Response({'ResultCode': 0, 'ResultDesc': 'Accepted'}, status=status.HTTP_200_OK)


class MpesaSTKQueryView(APIView):
    """
    GET /api/billing/mpesa/query/?checkoutRequestId=ws_CO_...
    Polled by the frontend to check if user entered PIN or completed payment.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from .models import MpesaTransaction, Payment
        from .serializers import MpesaTransactionSerializer
        from .mpesa_service import get_facility_mpesa_config, query_stk_status_from_daraja
        from django.utils import timezone

        checkout_req_id = request.query_params.get('checkoutRequestId')
        if not checkout_req_id:
            return Response({'success': False, 'error': 'checkoutRequestId is required.'}, status=status.HTTP_400_BAD_REQUEST)

        txn = MpesaTransaction.objects.filter(checkout_request_id=checkout_req_id).first()
        if not txn:
            return Response({'success': False, 'error': 'Transaction not found.'}, status=status.HTTP_404_NOT_FOUND)

        # If already completed or failed, return status directly
        if txn.status in ['Completed', 'Failed', 'Cancelled']:
            return Response({
                'success': True,
                'data': MpesaTransactionSerializer(txn).data
            }, status=status.HTTP_200_OK)

        # Otherwise query Daraja API directly
        if txn.subscription_payment:
            config = None
        else:
            config = get_facility_mpesa_config(txn.facility or (txn.invoice.facility if txn.invoice else None))

        daraja_res = query_stk_status_from_daraja(config, checkout_req_id)

        if daraja_res and isinstance(daraja_res, dict):
            res_code = str(daraja_res.get('ResultCode', ''))
            res_desc = daraja_res.get('ResultDesc', '')

            if res_code == '0':
                txn.status = 'Completed'
                txn.result_code = 0
                txn.result_desc = res_desc
                txn.transaction_date = timezone.now()
                txn.save()

                if txn.invoice:
                    invoice = txn.invoice
                    payment_exists = Payment.objects.filter(
                        invoice=invoice, amount=txn.amount, method='M-Pesa'
                    ).exists()

                    if not payment_exists:
                        Payment.objects.create(
                            invoice=invoice,
                            amount=txn.amount,
                            method='M-Pesa',
                            status='Completed'
                        )
                        invoice.payment_method = 'M-Pesa'
                        invoice.save(update_fields=['payment_method'])
                        invoice.recalc_status()
                elif txn.subscription_payment:
                    from .mpesa_service import complete_subscription_payment
                    complete_subscription_payment(txn.subscription_payment)
            elif res_code in ['1032', '1037', '1', '2001']:
                txn.status = 'Cancelled' if res_code == '1032' else 'Failed'
                txn.result_code = int(res_code) if res_code.isdigit() else 1
                txn.result_desc = res_desc
                txn.save()
                if txn.subscription_payment:
                    txn.subscription_payment.status = 'failed'
                    txn.subscription_payment.notes = f"Payment failed: {res_desc}"
                    txn.subscription_payment.save()

        return Response({
            'success': True,
            'data': MpesaTransactionSerializer(txn).data
        }, status=status.HTTP_200_OK)