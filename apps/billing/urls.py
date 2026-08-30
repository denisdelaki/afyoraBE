from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import (
    InvoiceViewSet, PaymentViewSet,
    PatientPharmacyChargesView,
    PatientLabChargesView,
    PatientRadiologyChargesView,
    MpesaConfigView,
    MpesaSTKPushView,
    MpesaCallbackView,
    MpesaSTKQueryView,
)

router = DefaultRouter()
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('mpesa-config/', MpesaConfigView.as_view(), name='mpesa-config'),
    path('mpesa/stk-push/', MpesaSTKPushView.as_view(), name='mpesa-stk-push'),
    path('mpesa/callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
    path('mpesa/query/', MpesaSTKQueryView.as_view(), name='mpesa-stk-query'),
    path('patient-pharmacy-charges/', PatientPharmacyChargesView.as_view(), name='patient-pharmacy-charges'),
    path('patient-lab-charges/', PatientLabChargesView.as_view(), name='patient-lab-charges'),
    path('patient-radiology-charges/', PatientRadiologyChargesView.as_view(), name='patient-radiology-charges'),
    path('', include(router.urls)),
]