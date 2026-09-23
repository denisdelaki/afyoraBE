from rest_framework.routers import DefaultRouter
from .views import KNHTSConceptViewSet, MedicationHPTViewSet, TerminologyCatalogViewSet

router = DefaultRouter()
router.register(r'concepts', KNHTSConceptViewSet, basename='knhts-concept')
router.register(r'medications', MedicationHPTViewSet, basename='medication-hpt')
router.register(r'catalogs', TerminologyCatalogViewSet, basename='terminology-catalog')

urlpatterns = router.urls
