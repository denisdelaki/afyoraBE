from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PatientViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'', PatientViewSet, basename='patient')

urlpatterns = [
	path('', include(router.urls)),
]
