from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Facility
from patients.models import OutpatientTicket, Patient
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
		self.patient = Patient.objects.create(
			facility=self.facility,
			patient_id='P-100',
			first_name='John',
			last_name='Doe',
		)
		self.outpatient_ticket = OutpatientTicket.objects.create(
			facility=self.facility,
			patient=self.patient,
			ticket_number='OP-20261018-001',
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

	def _lab_request_payload(self, **overrides):
		payload = {
			'patient': 'John Doe',
			'patientId': self.patient.patient_id,
			'testId': self.test_obj.test_id,
			'orderedBy_employeeId': 'EMP-001',
			'orderedBy': 'Dr. Smith',
		}
		payload.update(overrides)
		return payload

	def test_create_lab_request_with_optional_ticket_number(self):
		response = self.client.post(
			f'/api/laboratory/requests/?facilityId={self.facility.id}',
			self._lab_request_payload(ticketNumber=self.outpatient_ticket.ticket_number),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		request_obj = LabRequest.objects.get(request_id=response.data['id'])
		self.assertEqual(request_obj.outpatient_ticket, self.outpatient_ticket)
		self.assertEqual(response.data['ticketNumber'], self.outpatient_ticket.ticket_number)

	def test_create_lab_request_compat_endpoint_with_frontend_aliases_and_ticket(self):
		response = self.client.post(
			f'/api/laboratory/labrequest/?facilityId={self.facility.id}',
			{
				'patient': self.patient.patient_id,
				'patientId': self.patient.patient_id,
				'ticketNumber': self.outpatient_ticket.ticket_number,
				'test': self.test_obj.test_id,
				'priority': 'Routine',
				'notes': 'bbj',
				'orderedBy': 'EMP003',
				'facilityId': str(self.facility.id),
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		request_obj = LabRequest.objects.get(request_id=response.data['id'])
		self.assertEqual(request_obj.outpatient_ticket, self.outpatient_ticket)
		self.assertEqual(request_obj.test, self.test_obj)
		self.assertEqual(request_obj.ordered_by_employee_id, 'EMP003')
		self.assertEqual(response.data['ticketNumber'], self.outpatient_ticket.ticket_number)

	def test_patch_lab_request_can_clear_ticket_number(self):
		self.request_obj.outpatient_ticket = self.outpatient_ticket
		self.request_obj.save(update_fields=['outpatient_ticket'])

		response = self.client.patch(
			f'/api/laboratory/labrequest/{self.request_obj.request_id}/?facilityId={self.facility.id}',
			{'ticketNumber': None},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
		self.request_obj.refresh_from_db()
		self.assertIsNone(self.request_obj.outpatient_ticket)
		self.assertIsNone(response.data['ticketNumber'])

	def test_create_lab_request_without_ticket_number_remains_supported(self):
		response = self.client.post(
			f'/api/laboratory/requests/?facilityId={self.facility.id}',
			self._lab_request_payload(),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		request_obj = LabRequest.objects.get(request_id=response.data['id'])
		self.assertIsNone(request_obj.outpatient_ticket)
		self.assertIsNone(response.data['ticketNumber'])

	def test_create_lab_request_rejects_ticket_for_a_different_patient(self):
		other_patient = Patient.objects.create(
			facility=self.facility,
			patient_id='P-200',
			first_name='Jane',
			last_name='Doe',
		)
		other_ticket = OutpatientTicket.objects.create(
			facility=self.facility,
			patient=other_patient,
			ticket_number='OP-20261018-002',
		)

		response = self.client.post(
			f'/api/laboratory/requests/?facilityId={self.facility.id}',
			self._lab_request_payload(ticketNumber=other_ticket.ticket_number),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('ticketNumber', response.data)

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
