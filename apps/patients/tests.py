from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Facility, User
from .models import OutpatientTicket, Patient, PatientVisit, PatientVital


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
			'nationalId': '12345678',
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
		self.assertEqual(response.data['nationalId'], '12345678')
		self.assertEqual(response.data['age'], 30)

	def test_create_patient_with_national_id_and_empty_email(self):
		payload = {
			'facilityId': self.facility.id,
			'nationalId': 'BC-998877',
			'firstName': 'Baby',
			'lastName': 'Doe',
			'gender': 'other',
			'age': 1,
			'email': '',
		}

		response = self.client.post('/api/patients/', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['nationalId'], 'BC-998877')
		self.assertEqual(response.data['email'], '')

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
			'diagnosisCode': 'I10',
			'diagnosisSystem': 'ICD-10-WHO',
			'diagnosisText': 'Hypertension Follow-up',
			'prescription': 'Amlodipine 5mg',
			'amountBilled': '2500.00',
			'whatHappened': 'Patient reported stable blood pressure levels.',
		}

		response = self.client.post('/api/patients/visits/', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(PatientVisit.objects.count(), 1)
		self.assertEqual(response.data['doctor'], 'Dr. Chen')
		self.assertEqual(response.data['patientId'], 'PAT0001')
		self.assertEqual(response.data['diagnosisCode'], 'I10')

	def test_create_patient_visit_requires_knhts_code_metadata(self):
		payload = {
			'facilityId': self.facility.id,
			'patientId': self.patient.patient_id,
			'date': '2024-02-20',
			'doctor': 'Dr. Chen',
			'diagnosis': 'Hypertension Follow-up',
			'amountBilled': '2500.00',
		}

		response = self.client.post('/api/patients/visits/', payload, format='json')

		self.assertEqual(response.status_code, 400)
		self.assertIn('diagnosisCode', response.data)

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
				'diagnosisCode': 'Z00.00',
				'diagnosisSystem': 'ICD-10-WHO',
				'diagnosisText': 'Routine Checkup',
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
			'diagnosisCode': 'I10',
			'diagnosisSystem': 'ICD-10-WHO',
			'diagnosisText': 'Hypertension Follow-up',
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
			{
				'diagnosis': 'Routine Follow-up',
				'diagnosisCode': 'Z00.00',
				'diagnosisSystem': 'ICD-10-WHO',
				'diagnosisText': 'Routine Follow-up',
			},
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
				'diagnosisCode': 'Z00.01',
				'diagnosisSystem': 'ICD-10-WHO',
				'diagnosisText': 'Annual Checkup',
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


class OutpatientTicketAPITests(TestCase):
	def setUp(self):
		self.facility = Facility.objects.create(name='Queue Clinic', facility_type='clinic', registration_number='REG-QUEUE', email='queue@example.com', phone='0700000001')
		self.receptionist = User.objects.create_user(username='queue-reception', password='StrongPass123!', facility=self.facility, role='receptionist')
		self.doctor = User.objects.create_user(username='queue-doctor', password='StrongPass123!', facility=self.facility, role='doctor')
		self.lab_technician = User.objects.create_user(username='queue-lab', password='StrongPass123!', facility=self.facility, role='lab_technician')
		self.patient = Patient.objects.create(facility=self.facility, patient_id='PAT-QUEUE', first_name='Queue', last_name='Patient')
		self.client = APIClient()

	def test_ticket_moves_from_consultation_to_laboratory_and_completes(self):
		self.client.force_authenticate(user=self.receptionist)
		created = self.client.post('/api/patients/tickets/', {
			'facilityId': self.facility.id, 'patientId': self.patient.patient_id,
			'destination': 'consultation', 'assignedTo': self.doctor.id,
		}, format='json')
		self.assertEqual(created.status_code, 201)
		ticket_id = created.data['id']
		self.assertTrue(created.data['ticketNumber'].startswith('OP-'))
		self.assertEqual(len(created.data['movements']), 1)

		self.client.force_authenticate(user=self.doctor)
		called = self.client.post(f'/api/patients/tickets/{ticket_id}/call/?facilityId={self.facility.id}', {}, format='json')
		self.assertEqual(called.status_code, 200)
		forwarded = self.client.post(
			f'/api/patients/tickets/{ticket_id}/forward/?facilityId={self.facility.id}',
			{'destination': 'laboratory', 'assignedTo': self.lab_technician.id, 'notes': 'FBC requested'}, format='json',
		)
		self.assertEqual(forwarded.status_code, 200)
		self.assertEqual(forwarded.data['destination'], 'laboratory')
		self.assertEqual(forwarded.data['status'], 'waiting')
		self.assertEqual(len(forwarded.data['movements']), 2)

		self.client.force_authenticate(user=self.lab_technician)
		self.client.post(f'/api/patients/tickets/{ticket_id}/call/?facilityId={self.facility.id}', {}, format='json')
		completed = self.client.post(f'/api/patients/tickets/{ticket_id}/complete/?facilityId={self.facility.id}', {}, format='json')
		self.assertEqual(completed.status_code, 200)
		self.assertEqual(completed.data['status'], 'completed')
		self.assertIsNotNone(completed.data['completedAt'])
		self.assertEqual(OutpatientTicket.objects.get(id=ticket_id).movements.count(), 2)


class PatientVitalAPITests(TestCase):
	def setUp(self):
		self.facility1 = Facility.objects.create(
			name='Kenyatta National Hospital',
			facility_type='hospital',
			registration_number='REG-KNH-001',
			email='knh@example.com',
			phone='0711111111',
		)
		self.facility2 = Facility.objects.create(
			name='Aga Khan Hospital',
			facility_type='hospital',
			registration_number='REG-AKH-002',
			email='akh@example.com',
			phone='0722222222',
		)

		self.nurse_jane = User.objects.create_user(
			username='nurse_jane',
			first_name='Jane',
			last_name='Wanjiku',
			email='jane@knh.or.ke',
			password='StrongPass123!',
			facility=self.facility1,
			role='nurse',
		)
		self.doctor_bob = User.objects.create_user(
			username='doctor_bob',
			first_name='Bob',
			last_name='Otieno',
			email='bob@knh.or.ke',
			password='StrongPass123!',
			facility=self.facility1,
			role='doctor',
		)
		self.other_user = User.objects.create_user(
			username='other_user',
			email='other@akh.or.ke',
			password='StrongPass123!',
			facility=self.facility2,
			role='nurse',
		)

		self.patient = Patient.objects.create(
			facility=self.facility1,
			patient_id='PAT-VITAL-001',
			first_name='Peter',
			last_name='Kamau',
			phone='0733333333',
		)

		self.client = APIClient()

	def test_create_patient_vitals_by_specific_nurse(self):
		self.client.force_authenticate(user=self.nurse_jane)
		payload = {
			'facilityId': self.facility1.id,
			'patientId': self.patient.patient_id,
			'temperatureC': 37.5,
			'systolicBp': 120,
			'diastolicBp': 80,
			'heartRateBpm': 72,
			'respiratoryRate': 16,
			'spo2Percent': 98,
			'bloodGlucoseMmol': 5.4,
			'heightCm': 175.0,
			'weightKg': 70.0,
			'painScore': 2,
			'notes': 'Patient resting comfortably.',
		}

		response = self.client.post('/api/patients/vitals/', payload, format='json')

		self.assertEqual(response.status_code, 201)
		self.assertEqual(PatientVital.objects.count(), 1)

		vital = PatientVital.objects.first()
		self.assertEqual(vital.patient, self.patient)
		self.assertEqual(vital.facility, self.facility1)
		self.assertEqual(vital.captured_by, self.nurse_jane)
		self.assertEqual(vital.captured_by_name, 'Jane Wanjiku')
		self.assertEqual(float(vital.temperature_c), 37.5)
		self.assertEqual(vital.systolic_bp, 120)
		self.assertEqual(vital.diastolic_bp, 80)
		self.assertEqual(float(vital.bmi), 22.9)  # auto-computed 70 / (1.75^2)

	def test_fetch_vitals_for_patient(self):
		self.client.force_authenticate(user=self.doctor_bob)

		vital = PatientVital.objects.create(
			facility=self.facility1,
			patient=self.patient,
			captured_by=self.nurse_jane,
			captured_by_name='Nurse Jane Wanjiku',
			temperature_c=38.2,
			systolic_bp=135,
			diastolic_bp=88,
			heart_rate_bpm=88,
			spo2_percent=95,
		)

		# Fetch via general vitals endpoint with patientId filter
		response = self.client.get(
			f'/api/patients/vitals/?facilityId={self.facility1.id}&patientId={self.patient.patient_id}'
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['id'], vital.id)
		self.assertEqual(response.data['results'][0]['capturedBy']['fullName'], 'Jane Wanjiku')

		# Fetch via patient-nested vitals endpoint
		nested_response = self.client.get(
			f'/api/patients/{self.patient.patient_id}/vitals/?facilityId={self.facility1.id}'
		)
		self.assertEqual(nested_response.status_code, 200)
		self.assertEqual(nested_response.data['count'], 1)
		self.assertEqual(nested_response.data['results'][0]['id'], vital.id)

	def test_save_and_fetch_vitals_without_consultation_for_ticket(self):
		self.client.force_authenticate(user=self.nurse_jane)
		ticket = OutpatientTicket.objects.create(
			facility=self.facility1, patient=self.patient, ticket_number='VITAL-001',
		)
		other_ticket = OutpatientTicket.objects.create(
			facility=self.facility1, patient=self.patient, ticket_number='VITAL-002',
		)
		PatientVital.objects.create(
			facility=self.facility1, patient=self.patient, ticket=other_ticket, systolic_bp=130,
		)
		PatientVital.objects.create(facility=self.facility1, patient=self.patient, systolic_bp=140)
		response = self.client.post(
			f'/api/patients/{self.patient.patient_id}/vitals/',
			{'facilityId': self.facility1.id, 'ticketId': str(ticket.id), 'painScore': 0},
			format='json',
		)
		self.assertEqual(response.status_code, 201, response.data)
		vital = PatientVital.objects.get(id=response.data['id'])
		self.assertEqual(vital.ticket, ticket)
		self.assertIsNone(vital.visit)
		self.assertEqual(vital.pain_score, 0)
		for endpoint in ('/api/patients/vitals/', f'/api/patients/{self.patient.patient_id}/vitals/'):
			fetched = self.client.get(
				f'{endpoint}?facilityId={self.facility1.id}&patientId={self.patient.patient_id}&ticketId={ticket.id}',
			)
			self.assertEqual(fetched.status_code, 200, fetched.data)
			self.assertEqual(fetched.data['count'], 1)
			self.assertEqual(fetched.data['results'][0]['id'], vital.id)
			self.assertEqual(fetched.data['results'][0]['ticketId'], ticket.id)

	def test_reject_vitals_for_another_patients_ticket(self):
		self.client.force_authenticate(user=self.nurse_jane)
		other_patient = Patient.objects.create(
			facility=self.facility1, patient_id='PAT-VITAL-002', first_name='Other', last_name='Patient',
		)
		ticket = OutpatientTicket.objects.create(
			facility=self.facility1, patient=other_patient, ticket_number='VITAL-OTHER',
		)
		response = self.client.post('/api/patients/vitals/', {
			'facilityId': self.facility1.id, 'patientId': self.patient.patient_id,
			'ticketId': ticket.id, 'systolicBp': 120,
		}, format='json')
		self.assertEqual(response.status_code, 400)
		self.assertIn('ticketId', response.data)
		self.assertEqual(PatientVital.objects.count(), 0)

	def test_reject_vitals_for_another_facilitys_ticket(self):
		self.client.force_authenticate(user=self.nurse_jane)
		other_patient = Patient.objects.create(
			facility=self.facility2, patient_id='PAT-OTHER-FACILITY', first_name='Other', last_name='Patient',
		)
		ticket = OutpatientTicket.objects.create(
			facility=self.facility2, patient=other_patient, ticket_number='VITAL-OTHER-FACILITY',
		)
		response = self.client.post('/api/patients/vitals/', {
			'facilityId': self.facility1.id, 'patientId': self.patient.patient_id,
			'ticketId': ticket.id, 'systolicBp': 120,
		}, format='json')
		self.assertEqual(response.status_code, 400)
		self.assertIn('ticketId', response.data)

	def test_reject_invalid_ticket_filter(self):
		self.client.force_authenticate(user=self.doctor_bob)
		response = self.client.get(f'/api/patients/vitals/?facilityId={self.facility1.id}&ticketId=invalid')
		self.assertEqual(response.status_code, 400)
		self.assertIn('ticketId', response.data)

	def test_modify_vitals(self):
		self.client.force_authenticate(user=self.nurse_jane)

		vital = PatientVital.objects.create(
			facility=self.facility1,
			patient=self.patient,
			captured_by=self.nurse_jane,
			captured_by_name='Jane Wanjiku',
			temperature_c=36.8,
			systolic_bp=120,
			diastolic_bp=80,
		)

		patch_payload = {
			'facilityId': self.facility1.id,
			'temperatureC': 37.1,
			'systolicBp': 125,
			'notes': 'Re-checked after 15 mins rest.',
		}

		response = self.client.patch(
			f'/api/patients/vitals/{vital.id}/?facilityId={self.facility1.id}',
			patch_payload,
			format='json',
		)

		self.assertEqual(response.status_code, 200)
		vital.refresh_from_db()
		self.assertEqual(float(vital.temperature_c), 37.1)
		self.assertEqual(vital.systolic_bp, 125)
		self.assertEqual(vital.notes, 'Re-checked after 15 mins rest.')

	def test_facility_isolation_for_vitals(self):
		# Create vitals at Facility 1
		vital = PatientVital.objects.create(
			facility=self.facility1,
			patient=self.patient,
			captured_by=self.nurse_jane,
			temperature_c=37.0,
		)

		# Authenticate user from Facility 2 and attempt access
		self.client.force_authenticate(user=self.other_user)

		# Attempt GET list with Facility 2 ID
		response = self.client.get(f'/api/patients/vitals/?facilityId={self.facility2.id}')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 0)  # Facility 2 has no vitals

		# Attempt GET with Facility 1 ID should be denied due to user facility mismatch
		denied_response = self.client.get(f'/api/patients/vitals/?facilityId={self.facility1.id}')
		self.assertEqual(denied_response.status_code, 403)

