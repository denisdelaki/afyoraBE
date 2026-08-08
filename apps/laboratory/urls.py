from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LabRequestViewSet, LabResultViewSet, LabTestViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'tests', LabTestViewSet, basename='lab-test')
router.register(r'requests', LabRequestViewSet, basename='lab-request')
router.register(r'results', LabResultViewSet, basename='lab-result')

urlpatterns = [
	path('', include(router.urls)),
]
