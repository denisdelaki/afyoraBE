import requests
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Facility
from patients.models import OutpatientTicket, Patient

from .models import Drug, Prescription


class DrugTerminologyApiTests(APITestCase):
	def setUp(self):
		self.facility = Facility.objects.create(
			name='Pharmacy Test Facility',
			facility_type='hospital',
			registration_number='PHARM-TEST-001',
			email='pharmacy-test@example.com',
			phone='+254700000001',
		)
		self.user = get_user_model().objects.create_user(
			username='pharmacy-admin',
			email='pharmacy-admin@example.com',
			password='Password123!',
			facility=self.facility,
			role='facility_admin',
		)
		self.client.force_authenticate(user=self.user)

	@override_settings(
		KNHTS_BASE_URL='https://knhts.example/fhir',
		KNHTS_DRUG_VALUESET_URL='https://example.test/ValueSet/drugs',
	)
	@patch('core.knhts.requests.get')
	def test_drug_terminology_search_uses_drug_valueset(self, request_get):
		response = request_get.return_value
		response.raise_for_status.return_value = None
		response.json.return_value = {
			'resourceType': 'ValueSet',
			'expansion': {'contains': [{
				'system': 'https://example.test/CodeSystem/drugs',
				'code': 'AMOX500',
				'display': 'Amoxicillin 500 mg capsule',
			}]},
		}

		result = self.client.get('/api/pharmacy/drugs/terminology-search/?search=amox')

		self.assertEqual(result.status_code, status.HTTP_200_OK)
		self.assertEqual(result.data['data'][0]['code'], 'AMOX500')
		self.assertEqual(result.data['source'], 'knhts')
		self.assertEqual(
			request_get.call_args.kwargs['params'],
			{
				'filter': 'amox',
				'count': 20,
				'url': 'https://example.test/ValueSet/drugs',
			},
		)

	def test_create_coded_drug_persists_terminology_metadata(self):
		result = self.client.post('/api/pharmacy/drugs/', {
			'name': 'Amoxicillin 500 mg capsule',
			'drugCode': 'AMOX500',
			'drugSystem': 'https://example.test/CodeSystem/drugs',
			'stock': 10,
			'minStock': 2,
			'price': '15.00',
		}, format='json')

		self.assertEqual(result.status_code, status.HTTP_201_CREATED)
		drug = Drug.objects.get(facility=self.facility)
		self.assertEqual(drug.drug_code, 'AMOX500')
		self.assertEqual(drug.drug_system, 'https://example.test/CodeSystem/drugs')
		self.assertTrue(drug.is_coded)
		self.assertTrue(result.data['isCoded'])

	def test_create_coded_drug_accepts_terminology_suggestion_keys(self):
		result = self.client.post('/api/pharmacy/drugs/', {
			'name': 'Paracetamol 100 mg Oral Tablet',
			'code': 'GE10175',
			'system': 'https://fhir.dha.go.ke/terminology/CodeSystem/generic-products-cs',
			'stock': 668,
			'minStock': 78,
			'price': 979,
			'expiryDate': '2026-09-23',
			'manufacturer': 'jhk',
		}, format='json')

		self.assertEqual(result.status_code, status.HTTP_201_CREATED)
		drug = Drug.objects.get(facility=self.facility)
		self.assertEqual(drug.drug_code, 'GE10175')
		self.assertEqual(
			drug.drug_system,
			'https://fhir.dha.go.ke/terminology/CodeSystem/generic-products-cs',
		)
		self.assertTrue(drug.is_coded)
		self.assertEqual(result.data['drugCode'], 'GE10175')
		self.assertTrue(result.data['isCoded'])

	def test_create_manual_drug_is_flagged_uncoded(self):
		result = self.client.post('/api/pharmacy/drugs/', {
			'name': 'Locally compounded medicine',
			'stock': 1,
			'minStock': 0,
			'price': '10.00',
		}, format='json')

		self.assertEqual(result.status_code, status.HTTP_201_CREATED)
		drug = Drug.objects.get(facility=self.facility)
		self.assertFalse(drug.is_coded)
		self.assertEqual(drug.drug_code, '')
		self.assertFalse(result.data['isCoded'])

	def test_rejects_incomplete_drug_coding(self):
		result = self.client.post('/api/pharmacy/drugs/', {
			'name': 'Amoxicillin',
			'drugCode': 'AMOX500',
			'stock': 1,
			'minStock': 0,
			'price': '10.00',
		}, format='json')

		self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('drugSystem', result.data)

	def test_search_requires_at_least_two_characters(self):
		result = self.client.get('/api/pharmacy/drugs/terminology-search/?search=a')

		self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

	@patch('core.knhts.requests.get')
	def test_search_returns_empty_list_when_no_drugs_match(self, request_get):
		response = request_get.return_value
		response.raise_for_status.return_value = None
		response.json.return_value = {
			'resourceType': 'ValueSet',
			'expansion': {'contains': []},
		}

		result = self.client.get('/api/pharmacy/drugs/terminology-search/?search=zzzz')

		self.assertEqual(result.status_code, status.HTTP_200_OK)
		self.assertEqual(result.data, {'data': [], 'source': 'knhts'})

	@override_settings(KNHTS_BASE_URL='https://knhts.example/fhir')
	@patch('core.knhts.requests.get', side_effect=requests.RequestException('offline'))
	def test_search_failure_allows_manual_fallback(self, request_get):
		result = self.client.get('/api/pharmacy/drugs/terminology-search/?search=amox')

		self.assertEqual(result.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
		self.assertEqual(result.data['data'], [])
		self.assertEqual(result.data['source'], 'unavailable')
		self.assertIn('uncoded', result.data['detail'])


class PrescriptionTicketApiTests(APITestCase):
	def setUp(self):
		self.facility = Facility.objects.create(
			name='Prescription Ticket Facility',
			facility_type='hospital',
			registration_number='RX-TICKET-001',
			email='rx-ticket@example.com',
			phone='+254700000002',
		)
		self.user = get_user_model().objects.create_user(
			username='prescription-admin',
			email='prescription-admin@example.com',
			password='Password123!',
			facility=self.facility,
			role='facility_admin',
		)
		self.patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT-RX-001',
			first_name='Prescription',
			last_name='Patient',
		)
		self.ticket = OutpatientTicket.objects.create(
			facility=self.facility,
			patient=self.patient,
			ticket_number='OP-RX-001',
			destination='pharmacy',
		)
		self.client.force_authenticate(user=self.user)

	def _payload(self, **overrides):
		payload = {
			'patientId': self.patient.patient_id,
			'doctorId': 'DOC-RX-001',
			'drugs': [
				{'id': 'D001', 'name': 'Paracetamol', 'quantity': 2, 'dosage': '500mg'},
			],
		}
		payload.update(overrides)
		return payload

	def test_create_prescription_accepts_optional_ticket_number(self):
		response = self.client.post(
			'/api/pharmacy/prescriptions/',
			self._payload(ticketNumber=self.ticket.ticket_number),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		prescription = Prescription.objects.get()
		self.assertEqual(prescription.outpatient_ticket_id, self.ticket.id)
		self.assertEqual(response.data['ticketNumber'], self.ticket.ticket_number)

	def test_create_prescription_without_ticket_number_remains_supported(self):
		response = self.client.post(
			'/api/pharmacy/prescriptions/',
			self._payload(),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
		prescription = Prescription.objects.get()
		self.assertIsNone(prescription.outpatient_ticket_id)
		self.assertIsNone(response.data['ticketNumber'])

	def test_create_prescription_rejects_ticket_for_a_different_patient(self):
		other_patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT-RX-OTHER',
			first_name='Other',
			last_name='Patient',
		)
		other_ticket = OutpatientTicket.objects.create(
			facility=self.facility,
			patient=other_patient,
			ticket_number='OP-RX-OTHER',
			destination='pharmacy',
		)

		response = self.client.post(
			'/api/pharmacy/prescriptions/',
			self._payload(ticketNumber=other_ticket.ticket_number),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('ticketNumber', response.data)
		self.assertFalse(Prescription.objects.exists())

	def test_create_prescription_does_not_resolve_same_number_from_another_facility(self):
		other_facility = Facility.objects.create(
			name='Other Prescription Facility',
			facility_type='hospital',
			registration_number='RX-TICKET-002',
			email='rx-ticket-other@example.com',
			phone='+254700000003',
		)
		other_patient = Patient.objects.create(
			facility=other_facility,
			patient_id='PAT-RX-FACILITY-OTHER',
			first_name='Other',
			last_name='Facility',
		)
		OutpatientTicket.objects.create(
			facility=other_facility,
			patient=other_patient,
			ticket_number='OP-RX-CROSS-FACILITY',
			destination='pharmacy',
		)

		response = self.client.post(
			'/api/pharmacy/prescriptions/',
			self._payload(ticketNumber='OP-RX-CROSS-FACILITY'),
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn('ticketNumber', response.data)
		self.assertFalse(Prescription.objects.exists())
