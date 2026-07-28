from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Facility, User
from .models import Patient, PatientVisit


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


class PatientVisitAPITests(TestCase):
	def setUp(self):
		self.facility = Facility.objects.create(
			name='Afyora Referral',
			facility_type='hospital',
			registration_number='REG-200',
			email='referral@example.com',
			phone='0700999000',
		)
		self.user = User.objects.create_user(
			username='doctor_user',
			email='doctor@example.com',
			password='StrongPass123!',
			facility=self.facility,
			role='doctor',
		)
		self.patient = Patient.objects.create(
			facility=self.facility,
			patient_id='PAT0001',
			first_name='Mary',
			last_name='Maina',
		)
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)

	def test_create_patient_visit(self):
		payload = {
			'facilityId': self.facility.id,
			'patientId': self.patient.patient_id,
			'date': '2024-02-20',
			'doctor': 'Dr. Chen',
			'diagnosis': 'Hypertension Follow-up',
			'prescription': 'Amlodipine 5mg',
			'amountBilled': '2500.00',
			'whatHappened': 'Patient reported stable blood pressure levels.',
		}

		response = self.client.post('/api/patients/visits/', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(PatientVisit.objects.count(), 1)
		self.assertEqual(response.data['doctor'], 'Dr. Chen')
		self.assertEqual(response.data['patientId'], 'PAT0001')

	def test_list_patient_visits_for_patient(self):
		PatientVisit.objects.create(
			facility=self.facility,
			patient=self.patient,
			visit_date='2024-02-20',
			served_by='Dr. Chen',
			diagnosis='Hypertension Follow-up',
			prescription='Amlodipine 5mg',
			amount_billed='2500.00',
		)
		PatientVisit.objects.create(
			facility=self.facility,
			patient=self.patient,
			visit_date='2024-01-15',
			served_by='Dr. Wilson',
			diagnosis='Annual Checkup',
			prescription='None',
			amount_billed='0.00',
		)

		response = self.client.get(
			f'/api/patients/visits/?facilityId={self.facility.id}&patientId={self.patient.patient_id}'
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 2)
		self.assertEqual(response.data['results'][0]['doctor'], 'Dr. Chen')

	def test_update_patient_visit(self):
		visit = PatientVisit.objects.create(
			facility=self.facility,
			patient=self.patient,
			visit_date='2024-02-20',
			served_by='Dr. Chen',
			diagnosis='Hypertension Follow-up',
			prescription='Amlodipine 5mg',
			amount_billed='2500.00',
		)

		response = self.client.patch(
			f'/api/patients/visits/{visit.id}/?facilityId={self.facility.id}',
			{
				'diagnosis': 'Routine Checkup',
				'amountBilled': '3000.00',
			},
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		visit.refresh_from_db()
		self.assertEqual(visit.diagnosis, 'Routine Checkup')
		self.assertEqual(str(visit.amount_billed), '3000.00')

	def test_delete_patient_visit_soft_deletes(self):
		visit = PatientVisit.objects.create(
			facility=self.facility,
			patient=self.patient,
			visit_date='2024-02-20',
			served_by='Dr. Chen',
			diagnosis='Hypertension Follow-up',
			prescription='Amlodipine 5mg',
			amount_billed='2500.00',
		)

		response = self.client.delete(
			f'/api/patients/visits/{visit.id}/?facilityId={self.facility.id}'
		)

		self.assertEqual(response.status_code, 204)
		visit.refresh_from_db()
		self.assertFalse(visit.is_active)

	def test_list_visits_requires_facility_id(self):
		response = self.client.get('/api/patients/visits/')

		self.assertEqual(response.status_code, 400)
		self.assertIn('facilityId', response.data)

	def test_visit_history_create_and_list_by_patient_id(self):
		payload = {
			'facilityId': self.facility.id,
			'date': '2024-02-20',
			'doctor': 'Dr. Chen',
			'diagnosis': 'Hypertension Follow-up',
			'prescription': 'Amlodipine 5mg',
			'amountBilled': '2500.00',
		}

		create_response = self.client.post(
			f'/api/patients/{self.patient.patient_id}/visit-history/?facilityId={self.facility.id}/',
			payload,
			format='json',
		)

		self.assertEqual(create_response.status_code, 201)
		self.assertEqual(create_response.data['patientId'], self.patient.patient_id)

		list_response = self.client.get(
			f'/api/patients/{self.patient.patient_id}/visit-history/?facilityId={self.facility.id}/'
		)

		self.assertEqual(list_response.status_code, 200)
		self.assertEqual(list_response.data['count'], 1)
		self.assertEqual(list_response.data['results'][0]['doctor'], 'Dr. Chen')

	def test_visit_history_patch_put_and_delete_by_patient_id(self):
		visit = PatientVisit.objects.create(
			facility=self.facility,
			patient=self.patient,
			visit_date='2024-02-20',
			served_by='Dr. Chen',
			diagnosis='Hypertension Follow-up',
			prescription='Amlodipine 5mg',
			amount_billed='2500.00',
		)

		patch_response = self.client.patch(
			f'/api/patients/{self.patient.patient_id}/visit-history/{visit.id}/?facilityId={self.facility.id}/',
			{'diagnosis': 'Routine Follow-up'},
			format='json',
		)
		self.assertEqual(patch_response.status_code, 200)
		self.assertEqual(patch_response.data['diagnosis'], 'Routine Follow-up')

		put_response = self.client.put(
			f'/api/patients/{self.patient.patient_id}/visit-history/{visit.id}/?facilityId={self.facility.id}/',
			{
				'facilityId': self.facility.id,
				'patientId': self.patient.patient_id,
				'date': '2024-02-21',
				'doctor': 'Dr. Wilson',
				'diagnosis': 'Annual Checkup',
				'prescription': 'None',
				'amountBilled': '0.00',
				'whatHappened': 'General wellness check.',
			},
			format='json',
		)
		self.assertEqual(put_response.status_code, 200)
		self.assertEqual(put_response.data['doctor'], 'Dr. Wilson')

		delete_response = self.client.delete(
			f'/api/patients/{self.patient.patient_id}/visit-history/{visit.id}/?facilityId={self.facility.id}/'
		)
		self.assertEqual(delete_response.status_code, 204)

		visit.refresh_from_db()
		self.assertFalse(visit.is_active)
