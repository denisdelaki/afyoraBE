from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Facility
from .models import Employee


class EmployeeApiTests(APITestCase):
	def setUp(self):
		user_model = get_user_model()

		self.facility_one = Facility.objects.create(
			name='Facility One',
			facility_type='hospital',
			registration_number='F1-001',
			email='facility1@example.com',
			phone='+254700000001',
		)
		self.facility_two = Facility.objects.create(
			name='Facility Two',
			facility_type='clinic',
			registration_number='F2-001',
			email='facility2@example.com',
			phone='+254700000002',
		)

		self.user_one = user_model.objects.create_user(
			username='facility1-admin',
			email='admin1@example.com',
			password='StrongPass123!',
			facility=self.facility_one,
			role='facility_admin',
		)

		self.user_two = user_model.objects.create_user(
			username='facility2-admin',
			email='admin2@example.com',
			password='StrongPass123!',
			facility=self.facility_two,
			role='facility_admin',
		)

		self.employee_one = Employee.objects.create(
			facility=self.facility_one,
			employee_id='EMP001',
			name='Alice One',
			role='Doctor',
			department='Cardiology',
			email='alice@f1.com',
			phone='+254700000101',
			join_date='2024-01-10',
			salary='120000.00',
			status='Active',
			shift='Morning',
		)

		self.employee_two = Employee.objects.create(
			facility=self.facility_two,
			employee_id='EMP001',
			name='Bob Two',
			role='Nurse',
			department='ICU',
			email='bob@f2.com',
			phone='+254700000202',
			join_date='2024-01-11',
			salary='80000.00',
			status='Active',
			shift='Night',
		)

	def _authenticate(self, user):
		refresh = RefreshToken.for_user(user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

	def test_list_only_returns_same_facility_employees(self):
		self._authenticate(self.user_one)

		response = self.client.get('/api/employees/')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['name'], 'Alice One')

	def test_cannot_retrieve_other_facility_employee(self):
		self._authenticate(self.user_one)

		response = self.client.get(f'/api/employees/{self.employee_two.id}/')

		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_create_employee_is_attached_to_logged_in_facility(self):
		self._authenticate(self.user_one)

		payload = {
			'name': 'New Facility One Staff',
			'role': 'Lab Technician',
			'department': 'Laboratory',
			'email': 'new.staff@f1.com',
			'phone': '+254700001111',
			'joinDate': '2024-03-01',
			'salary': '65000.00',
			'status': 'Active',
			'shift': 'Evening',
		}

		response = self.client.post('/api/employees/', payload, format='json')

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		employee = Employee.objects.get(name='New Facility One Staff')
		self.assertEqual(employee.facility_id, self.facility_one.id)
