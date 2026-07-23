from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EmployeeViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'', EmployeeViewSet, basename='employee')

urlpatterns = [
	path('', include(router.urls)),
]
