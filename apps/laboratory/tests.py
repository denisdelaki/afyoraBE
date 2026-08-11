from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Facility
from .models import LabRequest, LabResult, LabTest


class LaboratoryApiTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()
		self.facility = Facility.objects.create(
			name='Test Facility',
			facility_type='hospital',
			registration_number='TEST-001',
			email='test@example.com',
			phone='+254700000001',
		)
		self.user = user_model.objects.create_user(
			username='lab-tech',
			email='labtech@example.com',
			password='Password123!',
			facility=self.facility,
			role='facility_admin',
		)
		self.client.force_authenticate(user=self.user)

		self.test_obj = LabTest.objects.create(
			facility=self.facility,
			test_id='T001',
			name='Complete Blood Count',
			category='Hematology',
			duration='30 mins',
			price=1500.00,
		)
		self.request_obj = LabRequest.objects.create(
			facility=self.facility,
			request_id='LAB-001',
			patient='John Doe',
			patient_id='P-100',
			test=self.test_obj,
			ordered_by_employee_id='EMP-001',
			ordered_by='Dr. Smith',
			order_date='2026-08-11',
			status='Pending',
			priority='Routine',
		)

	def test_labresult_compat_endpoint_post(self):
		url = f'/api/laboratory/labresult/?facilityId={self.facility.id}'
		payload = {
			'labRequest': 'LAB-001',
			'labId': 'LAB-001',
			'parameters': [
				{
					'name': 'Hemoglobin',
					'value': '14.5',
					'unit': 'g/dL',
					'range': '13.5-17.5',
					'status': 'Normal',
				}
			],
			'remarks': 'Normal test results',
		}
		response = self.client.post(url, payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['labId'], 'LAB-001')
		self.request_obj.refresh_from_db()
		self.assertEqual(self.request_obj.status, 'Completed')

	def test_start_lab_test(self):
		url = f'/api/laboratory/labrequest/{self.request_obj.request_id}/start/?facilityId={self.facility.id}'
		response = self.client.post(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.request_obj.refresh_from_db()
		self.assertEqual(self.request_obj.status, 'In Progress')

	def test_update_status_endpoint(self):
		url = f'/api/laboratory/labrequest/{self.request_obj.request_id}/status/?facilityId={self.facility.id}'
		payload = {'status': 'In Progress'}
		response = self.client.post(url, payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.request_obj.refresh_from_db()
		self.assertEqual(self.request_obj.status, 'In Progress')

	def test_patch_status_direct(self):
		url = f'/api/laboratory/labrequest/{self.request_obj.request_id}/?facilityId={self.facility.id}'
		payload = {'status': 'In Progress'}
		response = self.client.patch(url, payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.request_obj.refresh_from_db()
		self.assertEqual(self.request_obj.status, 'In Progress')

	def test_labtest_compat_endpoint_get(self):
		url = f'/api/laboratory/labtest/?facilityId={self.facility.id}'
		response = self.client.get(url)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertTrue(len(response.data) >= 1)
