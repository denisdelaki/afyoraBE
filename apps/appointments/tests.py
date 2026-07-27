from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Facility
from patients.models import Patient

from .models import Appointment


class AppointmentApiTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()

		self.facility_one = Facility.objects.create(
			name='Appointment Facility One',
			facility_type='hospital',
			registration_number='APT-F1-001',
			email='appointment-f1@example.com',
			phone='+254711111001',
		)
		self.facility_two = Facility.objects.create(
			name='Appointment Facility Two',
			facility_type='clinic',
			registration_number='APT-F2-001',
			email='appointment-f2@example.com',
			phone='+254711111002',
		)

		self.user_one = user_model.objects.create_user(
			username='appointment-admin-1',
			email='appointment-admin-1@example.com',
			password='StrongPass123!',
			facility=self.facility_one,
			role='facility_admin',
		)

		self.user_two = user_model.objects.create_user(
			username='appointment-admin-2',
			email='appointment-admin-2@example.com',
			password='StrongPass123!',
			facility=self.facility_two,
			role='facility_admin',
		)

		self.patient_one = Patient.objects.create(
			facility=self.facility_one,
			patient_id='PAT1001',
			first_name='Jane',
			last_name='Doe',
		)
		self.patient_two = Patient.objects.create(
			facility=self.facility_two,
			patient_id='PAT2001',
			first_name='John',
			last_name='Smith',
		)

		self.appointment_one = Appointment.objects.create(
			facility=self.facility_one,
			patient=self.patient_one,
			appointment_id='APT0001',
			date='2026-07-30',
			time='09:00:00',
			doctor='Dr. House',
			department='Cardiology',
			status='Scheduled',
		)
		self.appointment_two = Appointment.objects.create(
			facility=self.facility_two,
			patient=self.patient_two,
			appointment_id='APT0001',
			date='2026-08-01',
			time='10:30:00',
			doctor='Dr. Adams',
			department='ENT',
			status='Scheduled',
		)

	def _authenticate(self, user):
		refresh = RefreshToken.for_user(user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

	def test_create_appointment_in_user_facility(self):
		self._authenticate(self.user_one)

		payload = {
			'patientId': 'PAT1001',
			'date': '2026-08-05',
			'time': '14:30',
			'doctor': 'Dr. Wilson',
			'department': 'General Medicine',
		}

		response = self.client.post('/api/appointments/?facilityId=1/', payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data['patientId'], 'PAT1001')
		self.assertEqual(response.data['status'], 'Scheduled')

	def test_list_appointments_is_facility_scoped(self):
		self._authenticate(self.user_one)

		response = self.client.get('/api/appointments/?facilityId=1/')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['id'], 'APT0001')

	def test_update_appointment_for_same_facility(self):
		self._authenticate(self.user_one)

		payload = {
			'doctor': 'Dr. Updated',
			'department': 'Neurology',
			'time': '15:00',
			'status': 'Confirmed',
		}

		response = self.client.patch(
			f'/api/appointments/{self.appointment_one.appointment_id}/?facilityId=1/',
			payload,
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['doctor'], 'Dr. Updated')
		self.assertEqual(response.data['status'], 'Confirmed')

	def test_cancel_appointment(self):
		self._authenticate(self.user_one)

		response = self.client.patch(
			f'/api/appointments/{self.appointment_one.appointment_id}/cancel/?facilityId=1/',
			{},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['status'], 'Cancelled')

	def test_user_cannot_access_other_facility_appointment(self):
		self._authenticate(self.user_one)

		response = self.client.get('/api/appointments/?facilityId=2/')

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_filter_appointments_by_patient(self):
		self._authenticate(self.user_one)

		Appointment.objects.create(
			facility=self.facility_one,
			patient=self.patient_one,
			appointment_id='APT0002',
			date='2026-08-10',
			time='11:00:00',
			doctor='Dr. Another',
			department='Cardiology',
			status='Scheduled',
		)

		response = self.client.get('/api/appointments/?facilityId=1/&patientId=PAT1001')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 2)
