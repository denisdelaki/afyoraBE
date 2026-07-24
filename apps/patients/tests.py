from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Facility, User
from .models import Patient


class PatientAPITests(TestCase):
	def setUp(self):
		self.facility = Facility.objects.create(
			name='Afyora Clinic',
			facility_type='clinic',
			registration_number='REG-001',
			email='clinic@example.com',
			phone='0700000000',
		)
		self.user = User.objects.create_user(
			username='reception',
			email='reception@example.com',
			password='StrongPass123!',
			facility=self.facility,
			role='receptionist',
		)
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)

	def test_list_patients(self):
		patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT0001',
			first_name='Jane',
			last_name='Doe',
			phone='0700111222',
		)

		response = self.client.get(f'/api/patients/?facilityId={self.facility.id}')

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['id'], patient.patient_id)

	def test_create_patient(self):
		payload = {
			'facilityId': self.facility.id,
			'firstName': 'John',
			'lastName': 'Smith',
			'gender': 'male',
			'age': 30,
			'phone': '0700222333',
			'email': 'john@example.com',
		}

		response = self.client.post('/api/patients/', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(Patient.objects.count(), 1)
		self.assertTrue(response.data['id'].startswith('PAT'))
		self.assertEqual(response.data['firstName'], 'John')
		self.assertEqual(response.data['age'], 30)

	def test_create_patient_without_trailing_slash(self):
		payload = {
			'facilityId': self.facility.id,
			'firstName': 'Alice',
			'lastName': 'Brown',
			'gender': 'female',
			'phone': '0700123456',
		}

		response = self.client.post('/api/patients', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(Patient.objects.count(), 1)
		self.assertEqual(response.data['firstName'], 'Alice')

	def test_update_patient(self):
		patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT0001',
			first_name='Jane',
			last_name='Doe',
			phone='0700111222',
		)

		response = self.client.patch(
			f'/api/patients/{patient.patient_id}/?facilityId={self.facility.id}',
			{'phone': '0700999888'},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		patient.refresh_from_db()
		self.assertEqual(patient.phone, '0700999888')

	def test_delete_patient_soft_deletes(self):
		patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT0001',
			first_name='Jane',
			last_name='Doe',
			phone='0700111222',
		)

		response = self.client.delete(
			f'/api/patients/{patient.patient_id}/?facilityId={self.facility.id}'
		)

		self.assertEqual(response.status_code, 204)
		patient.refresh_from_db()
		self.assertFalse(patient.is_active)

	def test_list_patients_requires_facility_id(self):
		response = self.client.get('/api/patients/')

		self.assertEqual(response.status_code, 400)
		self.assertIn('facilityId', response.data)
