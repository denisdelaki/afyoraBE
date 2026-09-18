from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .views import (
	AllergyItemViewSet,
	CpoeOrderViewSet,
	EhrRecordViewSet,
	OutpatientTicketViewSet,
	PatientViewSet,
	PatientVisitViewSet,
	PatientVisitHistoryViewSet,
	ProblemItemViewSet,
)

router = DefaultRouter(trailing_slash='/?')
router.register(r'', PatientViewSet, basename='patient')

visit_router = DefaultRouter(trailing_slash='/?')
visit_router.register(r'', PatientVisitViewSet, basename='patient-visit')

ticket_router = DefaultRouter(trailing_slash='/?')
ticket_router.register(r'', OutpatientTicketViewSet, basename='outpatient-ticket')

problem_router = DefaultRouter(trailing_slash='/?')
problem_router.register(r'', ProblemItemViewSet, basename='problem-item')

allergy_router = DefaultRouter(trailing_slash='/?')
allergy_router.register(r'', AllergyItemViewSet, basename='allergy-item')

cpoe_router = DefaultRouter(trailing_slash='/?')
cpoe_router.register(r'', CpoeOrderViewSet, basename='cpoe-order')

urlpatterns = [
	re_path(
		r'^(?P<patient_id>[^/.]+)/visit-history/?$',
		PatientVisitHistoryViewSet.as_view({'get': 'list', 'post': 'create'}),
		name='patient-visit-history-list',
	),
	re_path(
		r'^(?P<patient_id>[^/.]+)/visit-history/(?P<visit_id>\d+)/?$',
		PatientVisitHistoryViewSet.as_view(
			{
				'get': 'retrieve',
				'put': 'update',
				'patch': 'partial_update',
				'delete': 'destroy',
			}
		),
		name='patient-visit-history-detail',
	),
	re_path(
		r'^(?P<patient_id>[^/.]+)/ehr/?$',
		EhrRecordViewSet.as_view({'get': 'list', 'post': 'create'}),
		name='patient-ehr-list',
	),
	re_path(
		r'^(?P<patient_id>[^/.]+)/ehr/(?P<ehr_id>\d+)/?$',
		EhrRecordViewSet.as_view(
			{
				'get': 'retrieve',
				'put': 'update',
				'patch': 'partial_update',
				'delete': 'destroy',
			}
		),
		name='patient-ehr-detail',
	),
	path('visits/', include(visit_router.urls)),
	path('tickets/', include(ticket_router.urls)),
	path('problems/', include(problem_router.urls)),
	path('allergies/', include(allergy_router.urls)),
	path('cpoe-orders/', include(cpoe_router.urls)),
	path('', include(router.urls)),
]
