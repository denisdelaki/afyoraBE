from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InsuranceProviderViewSet, DHALogViewSet,
    DHAEligibilityView, DHABenefitsView, DHAInterventionsView,
    DHAUtilizationView, DHASubBenefitsView, DHABedOccupancyView,
    DHAAuthorizationsView, DHARejectAuthorizationView, DHAVirtualClaimView,
    DHAClaimAttachmentsView, DHAClaimDiagnosesView, DHAClaimLinesView,
    DHAPrescriptionsView, DHAClaimDispatchView, DHAEmergencyClaimsView
)

router = DefaultRouter()
router.register(r'insurance-providers', InsuranceProviderViewSet, basename='insurance-provider')
router.register(r'logs', DHALogViewSet, basename='dha-log')

urlpatterns = [
    path('', include(router.urls)),

    # Benefits & Eligibility
    path('eligibility/', DHAEligibilityView.as_view(), name='dha-eligibility'),
    path('benefits/', DHABenefitsView.as_view(), name='dha-benefits'),
    path('benefits/interventions/', DHAInterventionsView.as_view(), name='dha-interventions'),
    path('benefits/utilization/', DHAUtilizationView.as_view(), name='dha-utilization'),
    path('sub-benefits/', DHASubBenefitsView.as_view(), name='dha-sub-benefits'),
    path('facilities/<str:facility_code>/beds/occupancy/', DHABedOccupancyView.as_view(), name='dha-bed-occupancy'),

    # Authorizations & Visit Consent
    path('claims/authorizations/', DHAAuthorizationsView.as_view(), name='dha-authorizations-get'),
    path('claims/authorize/', DHAAuthorizationsView.as_view(), name='dha-authorize-post'),
    path('claims/authorizations/<str:consent_token>/reject/', DHARejectAuthorizationView.as_view(), name='dha-authorize-reject'),
    path('claims/visit/', DHAVirtualClaimView.as_view(), name='dha-claim-visit'),

    # Billing, Line Items, Diagnoses, Attachments
    path('claims/attachments/', DHAClaimAttachmentsView.as_view(), name='dha-claim-attachments'),
    path('claims/diagnoses/', DHAClaimDiagnosesView.as_view(), name='dha-claim-diagnoses'),
    path('claims/lines/', DHAClaimLinesView.as_view(), name='dha-claim-lines'),
    path('claims/lines/edit/', DHAClaimLinesView.as_view(), name='dha-claim-lines-edit'),
    path('claims/lines/resubmit/', DHAClaimLinesView.as_view(), name='dha-claim-lines-resubmit'),

    # ePrescriptions
    path('prescriptions/', DHAPrescriptionsView.as_view(), name='dha-prescriptions'),
    path('prescriptions/dispenses/', DHAPrescriptionsView.as_view(), name='dha-prescription-dispenses'),
    path('prescriptions/doctors/', DHAPrescriptionsView.as_view(), name='dha-prescription-doctors'),

    # Dispatch & Discharge
    path('claims/close/', DHAClaimDispatchView.as_view(), name='dha-claim-close'),
    path('claims/discharge/', DHAClaimDispatchView.as_view(), name='dha-claim-discharge'),
    path('claims/otp/discharge/', DHAClaimDispatchView.as_view(), name='dha-claim-otp-discharge'),
    path('claims/submit/', DHAClaimDispatchView.as_view(), name='dha-claim-submit'),
    path('patients/next-of-kin/contacts/', DHAClaimDispatchView.as_view(), name='dha-next-of-kin'),

    # Emergency & EMT
    path('claims/doctors/', DHAEmergencyClaimsView.as_view(), name='dha-emergency-doctors'),
    path('claims/emergency/', DHAEmergencyClaimsView.as_view(), name='dha-emergency-claim'),
    path('claims/emergency/protocols/', DHAEmergencyClaimsView.as_view(), name='dha-emergency-protocols'),
    path('claims/emt/', DHAEmergencyClaimsView.as_view(), name='dha-emt-claim'),
]
