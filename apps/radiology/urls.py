from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .views import ImagingStudyViewSet, ImagingRequestViewSet, ImagingReportViewSet, ImagingImageViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'studies', ImagingStudyViewSet, basename='radiology-study')
router.register(r'requests', ImagingRequestViewSet, basename='radiology-request')
router.register(r'reports', ImagingReportViewSet, basename='radiology-report')
router.register(r'images', ImagingImageViewSet, basename='radiology-image')

urlpatterns = [
    path('', include(router.urls)),
    # Compatibility routes for singular paths used by frontend
    re_path(r'^study/?$', ImagingStudyViewSet.as_view({'get': 'list', 'post': 'create'}), name='study-list-compat'),
    re_path(r'^study/(?P<study_id>[^/.]+)/?$', ImagingStudyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='study-detail-compat'),
    re_path(r'^request/?$', ImagingRequestViewSet.as_view({'get': 'list', 'post': 'create'}), name='request-list-compat'),
    re_path(r'^request/(?P<request_id>[^/.]+)/?$', ImagingRequestViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='request-detail-compat'),
    re_path(r'^request/(?P<request_id>[^/.]+)/status/?$', ImagingRequestViewSet.as_view({'post': 'status', 'patch': 'status', 'put': 'status'}), name='request-status-compat'),
    re_path(r'^request/(?P<request_id>[^/.]+)/schedule/?$', ImagingRequestViewSet.as_view({'post': 'schedule', 'patch': 'schedule'}), name='request-schedule-compat'),
    re_path(r'^report/?$', ImagingReportViewSet.as_view({'get': 'list', 'post': 'create'}), name='report-list-compat'),
    re_path(r'^report/(?P<report_id>[^/.]+)/?$', ImagingReportViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='report-detail-compat'),
]

