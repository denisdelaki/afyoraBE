from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DrugViewSet, PrescriptionViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'drugs', DrugViewSet, basename='drug')
router.register(r'prescriptions', PrescriptionViewSet, basename='prescription')

urlpatterns = [
	path('', include(router.urls)),
]
