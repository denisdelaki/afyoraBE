from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .views import LabRequestViewSet, LabResultViewSet, LabTestViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'tests', LabTestViewSet, basename='lab-test')
router.register(r'requests', LabRequestViewSet, basename='lab-request')
router.register(r'results', LabResultViewSet, basename='lab-result')

urlpatterns = [
	path('', include(router.urls)),
	# Compatibility routes for singular resource paths used by frontend
	re_path(r'^labtest/?$', LabTestViewSet.as_view({'get': 'list', 'post': 'create'}), name='labtest-list-compat'),
	re_path(r'^labtest/(?P<test_id>[^/.]+)/?$', LabTestViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='labtest-detail-compat'),
	re_path(r'^labrequest/?$', LabRequestViewSet.as_view({'get': 'list', 'post': 'create'}), name='labrequest-list-compat'),
	re_path(r'^labrequest/(?P<request_id>[^/.]+)/?$', LabRequestViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='labrequest-detail-compat'),
	re_path(r'^labrequest/(?P<request_id>[^/.]+)/start/?$', LabRequestViewSet.as_view({'post': 'start', 'patch': 'start'}), name='labrequest-start-compat'),
	re_path(r'^labrequest/(?P<request_id>[^/.]+)/status/?$', LabRequestViewSet.as_view({'post': 'status', 'patch': 'status', 'put': 'status'}), name='labrequest-status-compat'),
	re_path(r'^labrequest/(?P<request_id>[^/.]+)/approve/?$', LabRequestViewSet.as_view({'post': 'approve', 'patch': 'approve'}), name='labrequest-approve-compat'),
	re_path(r'^labresult/?$', LabResultViewSet.as_view({'get': 'list', 'post': 'create'}), name='labresult-list-compat'),
	re_path(r'^labresult/(?P<lab_id>[^/.]+)/?$', LabResultViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='labresult-detail-compat'),
]
