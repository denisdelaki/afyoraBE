import requests
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Facility
from .models import Drug


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
