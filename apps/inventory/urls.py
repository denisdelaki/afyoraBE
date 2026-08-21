from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VendorViewSet, SupplyViewSet, EquipmentViewSet, PurchaseOrderViewSet

router = DefaultRouter()
router.register(r'vendors', VendorViewSet, basename='vendor')
router.register(r'supplies', SupplyViewSet, basename='supply')
router.register(r'equipment', EquipmentViewSet, basename='equipment')
router.register(r'orders', PurchaseOrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
]
