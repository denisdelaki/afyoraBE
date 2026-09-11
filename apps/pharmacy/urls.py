from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DrugCategoryViewSet, DrugPurchaseOrderViewSet, DrugViewSet, PrescriptionViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'categories', DrugCategoryViewSet, basename='category')
router.register(r'drugs', DrugViewSet, basename='drug')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')
router.register(r'purchase-orders', DrugPurchaseOrderViewSet, basename='drug-purchase-order')

urlpatterns = [
	path('', include(router.urls)),
]
