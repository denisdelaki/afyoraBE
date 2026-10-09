from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	FacilitySearchView,
	HieConnectionPingView,
	HieConnectionView,
	HieMaturityLevelsView,
	HieMaturityUpgradeView,
	HieSyncLogViewSet,
	QualityMeasureViewSet,
	TerminologyStandardViewSet,
)

router = DefaultRouter(trailing_slash='/?')
router.register(r'terminology-standards', TerminologyStandardViewSet, basename='terminology-standard')
router.register(r'quality-measures', QualityMeasureViewSet, basename='quality-measure')
router.register(r'sync-logs', HieSyncLogViewSet, basename='hie-sync-log')

urlpatterns = [
	path('facilities/search/', FacilitySearchView.as_view(), name='facility-search'),
	path('hie-connection/', HieConnectionView.as_view(), name='hie-connection'),
	path('hie-connection/ping/', HieConnectionPingView.as_view(), name='hie-connection-ping'),
	path('maturity-levels/', HieMaturityLevelsView.as_view(), name='maturity-levels'),
	path('maturity-levels/upgrade/', HieMaturityUpgradeView.as_view(), name='maturity-levels-upgrade'),
	path('', include(router.urls)),
]
