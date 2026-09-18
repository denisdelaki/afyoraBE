from rest_framework.routers import DefaultRouter

from .views import IdsrWeeklyReportViewSet, NotifiableDiseaseAlertViewSet, PublicHealthEventViewSet

router = DefaultRouter(trailing_slash='/?')
router.register(r'notifiable-alerts', NotifiableDiseaseAlertViewSet, basename='notifiable-alert')
router.register(r'idsr-weekly', IdsrWeeklyReportViewSet, basename='idsr-weekly')
router.register(r'public-events', PublicHealthEventViewSet, basename='public-event')

urlpatterns = router.urls
