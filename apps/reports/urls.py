from django.urls import path
from .views import (
    ReportDataAPIView,
    SavedReportDetailAPIView,
    SavedReportListCreateAPIView,
)

urlpatterns = [
    path('data/', ReportDataAPIView.as_view(), name='report-data'),
    path('saved/', SavedReportListCreateAPIView.as_view(), name='saved-report-list'),
    path('saved/<int:pk>/', SavedReportDetailAPIView.as_view(), name='saved-report-detail'),
]
