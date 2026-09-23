import datetime
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InsuranceProvider, DHAClaim, DHAAuthorization, DHAPrescription, DHAEmergencyClaim, DHALog
from .serializers import (
    InsuranceProviderSerializer, DHAClaimSerializer, DHAAuthorizationSerializer,
    DHAPrescriptionSerializer, DHAEmergencyClaimSerializer, DHALogSerializer,
    EligibilityQuerySerializer, AuthorizeRequestSerializer, VisitRequestSerializer,
    ClaimAttachmentSerializer, ClaimDiagnosisSerializer, ClaimLineItemSerializer,
    PrescriptionCreateSerializer, DispenseCreateSerializer, DischargeRequestSerializer,
    CloseClaimSerializer, EmergencyCaseSerializer, EMTClaimSerializer
)
from .services import DHAAfyaConnectClient


class InsuranceProviderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Facility Admins to onboard and configure insurance services
    such as Social Health Authority (SHA / DHA AfyaConnect), NHIF, and private payers.
    """
    queryset = InsuranceProvider.objects.all()
    serializer_class = InsuranceProviderSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post'], url_path='ping')
    def ping_gateway(self, request, pk=None):
        """Test health connection latency & ping the DHA gateway."""
        provider = self.get_object()
        client = DHAAfyaConnectClient(provider_code=provider.code)
        
        # Test pinging SHA eligibility or root health endpoint
        resp_data, status_code = client.request(
            'GET',
            'api/v1/patients/eligibility',
            params={'identification_number': '32849201', 'identification_type': 'National ID'}
        )
        
        provider.last_ping_at = datetime.datetime.now()
        if status_code in [200, 201]:
            provider.last_ping_status = "Healthy (200 OK)"
        else:
            provider.last_ping_status = f"Warning ({status_code})"
        provider.save()

        return Response({
            "status": "success",
            "provider": provider.name,
            "gateway_url": provider.gateway_url,
            "last_ping_status": provider.last_ping_status,
            "last_ping_at": provider.last_ping_at,
            "gateway_response": resp_data
        })


class DHAEligibilityView(APIView):
    """GET /api/v1/patients/eligibility"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        id_num = request.query_params.get('identification_number')
        id_type = request.query_params.get('identification_type', 'National ID')
        if not id_num:
            return Response({"error": "identification_number query param is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/patients/eligibility',
            params={'identification_number': id_num, 'identification_type': id_type}
        )
        return Response(data, status=status_code)


class DHABenefitsView(APIView):
    """GET /api/v1/patients/benefits"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/patients/benefits',
            params={
                'patient_id': patient_id,
                'fields': request.query_params.get('fields', 'parent_benefit,parent_benefit_code'),
                'is_unique_benefit': request.query_params.get('is_unique_benefit', 'false')
            }
        )
        return Response(data, status=status_code)


class DHAInterventionsView(APIView):
    """GET /api/v1/patients/benefits/interventions"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        sub_code = request.query_params.get('sub_benefit_code')
        if not patient_id or not sub_code:
            return Response({"error": "patient_id and sub_benefit_code are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/patients/benefits/interventions',
            params={'patient_id': patient_id, 'sub_benefit_code': sub_code}
        )
        return Response(data, status=status_code)


class DHAUtilizationView(APIView):
    """GET /api/v1/patients/benefits/utilization"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        intervention_code = request.query_params.get('intervention_code')
        if not patient_id or not intervention_code:
            return Response({"error": "patient_id and intervention_code are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/patients/benefits/utilization',
            params={'patient_id': patient_id, 'intervention_code': intervention_code}
        )
        return Response(data, status=status_code)


class DHASubBenefitsView(APIView):
    """GET /api/v1/patients/sub-benefits"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        patient_id = request.query_params.get('patient_id')
        if not patient_id:
            return Response({"error": "patient_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/patients/sub-benefits',
            params={'patient_id': patient_id}
        )
        return Response(data, status=status_code)


class DHABedOccupancyView(APIView):
    """GET /api/v1/facilities/{facilityCode}/beds/occupancy"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, facility_code):
        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            f'api/v1/facilities/{facility_code}/beds/occupancy'
        )
        return Response(data, status=status_code)


class DHAAuthorizationsView(APIView):
    """
    Authorizations endpoints:
    GET /api/v1/claims/authorizations
    POST /api/v1/claims/authorize
    POST /api/v1/claims/authorizations/{consent_token}/reject
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        guid = request.query_params.get('guid')
        if not token or not guid:
            return Response({"error": "token and guid query parameters are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'GET',
            'api/v1/claims/authorizations',
            params={'token': token, 'guid': guid, 'beneficiary_code': request.query_params.get('beneficiary_code', '')}
        )
        return Response(data, status=status_code)

    def post(self, request):
        serializer = AuthorizeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'POST',
            'api/v1/claims/authorize',
            json_data=serializer.validated_data
        )

        # Save to local DHAAuthorization DB model
        try:
            DHAAuthorization.objects.create(
                guid=data.get('guid') or f"guid-{datetime.datetime.now().timestamp()}",
                auth_code=data.get('authCode', 'AUTH-NEW'),
                token=data.get('token', 'TOK-DHA-9901'),
                patient_id=serializer.validated_data['patient_id'],
                beneficiary_name=data.get('beneficiaryName', serializer.validated_data.get('patient_name', 'Patient')),
                service_type=serializer.validated_data['service_type'],
                status=data.get('status', 'APPROVED'),
                interventions=serializer.validated_data['interventions']
            )
        except Exception as err:
            pass

        return Response(data, status=status_code)


class DHARejectAuthorizationView(APIView):
    """POST /api/v1/claims/authorizations/{consent_token}/reject"""
    permission_classes = [permissions.AllowAny]

    def post(self, request, consent_token):
        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'POST',
            f'api/v1/claims/authorizations/{consent_token}/reject'
        )
        return Response(data, status=status_code)


class DHAVirtualClaimView(APIView):
    """POST /api/v1/claims/visit - Create new virtual claim / Start Visit"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VisitRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'POST',
            'api/v1/claims/visit',
            json_data=serializer.validated_data
        )

        # Save local DHAClaim record
        try:
            DHAClaim.objects.create(
                claim_id=str(data.get('id', '')),
                authorization_code=data.get('authorization_code', f"TOK-{request.data.get('otp', '1234')}"),
                authorization_guid=data.get('authorization_guid', ''),
                patient_id=serializer.validated_data['patient_id'],
                patient_name=data.get('patient_name', 'Beneficiary Patient'),
                member_number=data.get('member_number', serializer.validated_data['patient_id']),
                service_type=serializer.validated_data['service_type'],
                workflow_state=data.get('workflow_state', 'OPEN'),
                invoice_number=data.get('invoice_number', f"INV-{data.get('id', '9901')}"),
                total_claim_amount=data.get('total_claim_amount', 0.00),
                total_claim_net_amount=data.get('total_claim_net_amount', 0.00),
                interventions=serializer.validated_data['intervention_codes']
            )
        except Exception:
            pass

        return Response(data, status=status_code)


class DHAClaimAttachmentsView(APIView):
    """POST /api/v1/claims/attachments & PATCH /api/v1/claims/attachments"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ClaimAttachmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'POST',
            'api/v1/claims/attachments',
            json_data=serializer.validated_data
        )
        return Response(data, status=status_code)

    def patch(self, request):
        attachment_id = request.data.get('attachment_id')
        consent_token = request.data.get('consent_token')
        intervention_code = request.data.get('intervention_code')
        if not attachment_id or not consent_token or not intervention_code:
            return Response({"error": "attachment_id, consent_token, and intervention_code are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'PATCH',
            'api/v1/claims/attachments',
            json_data=request.data
        )
        return Response(data, status=status_code)


class DHAClaimDiagnosesView(APIView):
    """POST /api/v1/claims/diagnoses & PATCH /api/v1/claims/diagnoses"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ClaimDiagnosisSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'POST',
            'api/v1/claims/diagnoses',
            json_data=serializer.validated_data
        )
        return Response(data, status=status_code)

    def patch(self, request):
        consent_token = request.data.get('consent_token')
        icd_code = request.data.get('icd_code')
        intervention_code = request.data.get('intervention_code')
        if not consent_token or not icd_code or not intervention_code:
            return Response({"error": "consent_token, icd_code, and intervention_code are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request(
            'PATCH',
            'api/v1/claims/diagnoses',
            json_data=request.data
        )
        return Response(data, status=status_code)


class DHAClaimLinesView(APIView):
    """
    POST /api/v1/claims/lines
    PATCH /api/v1/claims/lines
    PATCH /api/v1/claims/lines/edit
    POST /api/v1/claims/lines/resubmit
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        if 'resubmit' in request.path:
            consent_token = request.data.get('consent_token')
            if not consent_token:
                return Response({"error": "consent_token is required"}, status=status.HTTP_400_BAD_REQUEST)
            client = DHAAfyaConnectClient()
            data, status_code = client.request('POST', 'api/v1/claims/lines/resubmit', json_data=request.data)
            return Response(data, status=status_code)

        serializer = ClaimLineItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request('POST', 'api/v1/claims/lines', json_data=serializer.validated_data)
        return Response(data, status=status_code)

    def patch(self, request):
        if 'edit' in request.path:
            line_id = request.data.get('line_id')
            if not line_id:
                return Response({"error": "line_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            client = DHAAfyaConnectClient()
            data, status_code = client.request('PATCH', 'api/v1/claims/lines/edit', json_data=request.data)
            return Response(data, status=status_code)

        consent_token = request.data.get('consent_token')
        line_guid = request.data.get('line_guid')
        if not consent_token or not line_guid:
            return Response({"error": "consent_token and line_guid are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request('PATCH', 'api/v1/claims/lines', json_data=request.data)
        return Response(data, status=status_code)


class DHAPrescriptionsView(APIView):
    """
    GET /api/v1/prescriptions
    POST /api/v1/prescriptions
    POST /api/v1/prescriptions/dispenses
    DELETE /api/v1/prescriptions/doctors
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        consent_token = request.query_params.get('consent_token')
        if not consent_token:
            return Response({"error": "consent_token query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request('GET', 'api/v1/prescriptions', params={'consent_token': consent_token})
        return Response(data, status=status_code)

    def post(self, request):
        if 'dispenses' in request.path:
            serializer = DispenseCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            client = DHAAfyaConnectClient()
            data, status_code = client.request('POST', 'api/v1/prescriptions/dispenses', json_data=serializer.validated_data)
            return Response(data, status=status_code)

        serializer = PrescriptionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request('POST', 'api/v1/prescriptions', json_data=serializer.validated_data)

        # Save local DHAPrescription
        try:
            DHAPrescription.objects.create(
                consent_token=serializer.validated_data['consent_token'],
                guid=data.get('guid', ''),
                code=data.get('code', 'RX-NEW'),
                intervention_code=serializer.validated_data['intervention_code'],
                items=serializer.validated_data['items']
            )
        except Exception:
            pass

        return Response(data, status=status_code)

    def delete(self, request):
        consent_token = request.data.get('consent_token')
        intervention_code = request.data.get('intervention_code')
        reg_num = request.data.get('practitioner_registration_number')
        if not consent_token or not intervention_code or not reg_num:
            return Response({"error": "consent_token, intervention_code, and practitioner_registration_number are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = DHAAfyaConnectClient()
        data, status_code = client.request('DELETE', 'api/v1/prescriptions/doctors', json_data=request.data)
        return Response(data, status=status_code)


class DHAClaimDispatchView(APIView):
    """
    POST /api/v1/claims/close
    POST /api/v1/claims/discharge
    POST /api/v1/claims/otp/discharge
    POST /api/v1/claims/submit
    POST /api/v1/patients/next-of-kin/contacts
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        client = DHAAfyaConnectClient()

        if 'close' in request.path:
            serializer = CloseClaimSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/close', json_data=serializer.validated_data)
            return Response(data, status=status_code)

        if 'otp/discharge' in request.path:
            consent_token = request.data.get('consent_token')
            patient_id = request.data.get('patient_id')
            if not consent_token or not patient_id:
                return Response({"error": "consent_token and patient_id are required"}, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/otp/discharge', json_data=request.data)
            return Response(data, status=status_code)

        if 'discharge' in request.path:
            serializer = DischargeRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/discharge', json_data=serializer.validated_data)
            return Response(data, status=status_code)

        if 'submit' in request.path:
            consent_token = request.data.get('consent_token')
            if not consent_token:
                return Response({"error": "consent_token is required"}, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/submit', json_data=request.data)
            return Response(data, status=status_code)

        if 'next-of-kin/contacts' in request.path:
            data, status_code = client.request('POST', 'api/v1/patients/next-of-kin/contacts', json_data=request.data)
            return Response(data, status=status_code)

        return Response({"error": "Invalid dispatch endpoint"}, status=status.HTTP_400_BAD_REQUEST)


class DHAEmergencyClaimsView(APIView):
    """
    POST /api/v1/claims/doctors
    DELETE /api/v1/claims/doctors
    POST /api/v1/claims/emergency
    GET & POST /api/v1/claims/emergency/protocols
    POST /api/v1/claims/emt
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if 'protocols' in request.path:
            active = request.query_params.get('active', 'true')
            intervention_code = request.query_params.get('intervention_code', 'INT-EMERG-01')
            client = DHAAfyaConnectClient()
            data, status_code = client.request('GET', 'api/v1/claims/emergency/protocols', params={'active': active, 'intervention_code': intervention_code})
            return Response(data, status=status_code)
        return Response({"error": "Method not allowed"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def post(self, request):
        client = DHAAfyaConnectClient()

        if 'emergency/protocols' in request.path:
            data, status_code = client.request('POST', 'api/v1/claims/emergency/protocols', json_data=request.data)
            return Response(data, status=status_code)

        if 'emt' in request.path:
            serializer = EMTClaimSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/emt', json_data=serializer.validated_data)
            return Response(data, status=status_code)

        if 'doctors' in request.path:
            data, status_code = client.request('POST', 'api/v1/claims/doctors', json_data=request.data)
            return Response(data, status=status_code)

        if 'emergency' in request.path:
            serializer = EmergencyCaseSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            data, status_code = client.request('POST', 'api/v1/claims/emergency', json_data=serializer.validated_data)
            
            # Save local DHAEmergencyClaim
            try:
                DHAEmergencyClaim.objects.create(
                    reference_number=serializer.validated_data['reference_number'],
                    brought_by=serializer.validated_data['brought_by'],
                    identification_number=serializer.validated_data['identification_number'],
                    mode_of_arrival=serializer.validated_data['mode_of_arrival'],
                    interventions=serializer.validated_data['interventions']
                )
            except Exception:
                pass

            return Response(data, status=status_code)

        return Response({"error": "Invalid emergency endpoint"}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        if 'doctors' in request.path:
            client = DHAAfyaConnectClient()
            data, status_code = client.request('DELETE', 'api/v1/claims/doctors', json_data=request.data)
            return Response(data, status=status_code)
        return Response({"error": "Invalid endpoint for DELETE"}, status=status.HTTP_400_BAD_REQUEST)


class DHALogViewSet(viewsets.ReadOnlyModelViewSet):
    """Security audit log viewset for DHA communication transmissions."""
    queryset = DHALog.objects.all()
    serializer_class = DHALogSerializer
    permission_classes = [permissions.AllowAny]
