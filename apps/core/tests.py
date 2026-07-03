from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Facility, FacilityOnboarding, User


class AuthViewTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_login_succeeds_for_admin_without_facility(self):
		user = User.objects.create_user(
			username='admin_no_facility',
			email='admin-no-facility@example.com',
			password='StrongPass123!',
			role='admin',
		)

		response = self.client.post(
			reverse('login'),
			{
				'email': user.email,
				'password': 'StrongPass123!',
				'remember_me': True,
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('access_token', response.data)
		self.assertIn('refresh_token', response.data)

	def test_authenticated_user_can_logout(self):
		user = User.objects.create_user(
			username='logout_user',
			email='logout-user@example.com',
			password='StrongPass123!',
			role='staff',
		)
		self.client.force_authenticate(user=user)

		response = self.client.post(reverse('logout'), {}, format='json')

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['message'], 'Logout successful')


class DepartmentViewSetTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_create_department_requires_user_facility(self):
		user = User.objects.create_user(
			username='staff_without_facility',
			email='staff@example.com',
			password='StrongPass123!',
			role='staff',
		)
		self.client.force_authenticate(user=user)

		response = self.client.post(
			reverse('department-list'),
			{
				'name': 'HR',
				'description': 'Human resource',
				'email': 'hr@example.com',
				'phone': '0703103852',
				'location': 'HQ',
				'is_operational': True,
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(
			response.data['detail'],
			'Your account is not assigned to a facility.'
		)


class FacilityViewSetTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_admin_can_create_facility(self):
		admin = User.objects.create_user(
			username='system_admin',
			email='system-admin@example.com',
			password='StrongPass123!',
			role='admin',
		)
		self.client.force_authenticate(user=admin)

		response = self.client.post(
			reverse('facility-list'),
			{
				'name': 'Sunrise Clinic',
				'facility_type': 'clinic',
				'registration_number': 'REG-2026-001',
				'email': 'hello@sunrise.test',
				'phone': '0700000000',
				'address': '123 Main Street',
				'city': 'Nairobi',
				'country': 'Kenya',
				'description': 'Primary care clinic',
				'website': 'https://sunrise.test',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		facility = Facility.objects.get(name='Sunrise Clinic')
		self.assertTrue(FacilityOnboarding.objects.filter(facility=facility).exists())
		self.assertEqual(response.data['id'], facility.id)
		self.assertEqual(response.data['registration_number'], 'REG-2026-001')
		self.assertEqual(response.data['departments_count'], 0)
		self.assertEqual(response.data['users_count'], 0)
		self.assertFalse(response.data['onboarding_completed'])

	def test_non_admin_cannot_create_facility(self):
		user = User.objects.create_user(
			username='staff_user',
			email='staff@example.com',
			password='StrongPass123!',
			role='staff',
		)
		self.client.force_authenticate(user=user)

		response = self.client.post(
			reverse('facility-list'),
			{
				'name': 'Blocked Clinic',
				'facility_type': 'clinic',
				'registration_number': 'REG-2026-002',
				'email': 'blocked@clinic.test',
				'phone': '0711111111',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(
			response.data['detail'],
			'Only administrators can create facilities.'
		)

	def test_admin_facility_add_page_renders(self):
		admin = User.objects.create_superuser(
			username='admin_site_user',
			email='admin-site@example.com',
			password='StrongPass123!',
		)
		admin.role = 'admin'
		admin.save(update_fields=['role'])

		self.client.force_login(admin)

		response = self.client.get(reverse('admin:core_facility_add'))

		self.assertEqual(response.status_code, status.HTTP_200_OK)

	def test_create_facility_rejects_duplicate_name(self):
		admin = User.objects.create_user(
			username='duplicate_name_admin',
			email='duplicate-name-admin@example.com',
			password='StrongPass123!',
			role='admin',
		)
		Facility.objects.create(
			name='Sunrise Clinic',
			facility_type='clinic',
			registration_number='REG-EXISTING-001',
			email='existing-name@example.com',
			phone='0700000001',
		)
		self.client.force_authenticate(user=admin)

		response = self.client.post(
			reverse('facility-list'),
			{
				'name': 'sunrise clinic',
				'facility_type': 'clinic',
				'registration_number': 'REG-2026-003',
				'email': 'new-name@example.com',
				'phone': '0722222222',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(
			response.data['name'][0],
			'A facility with this name already exists.'
		)

	def test_create_facility_rejects_duplicate_email(self):
		admin = User.objects.create_user(
			username='duplicate_email_admin',
			email='duplicate-email-admin@example.com',
			password='StrongPass123!',
			role='admin',
		)
		Facility.objects.create(
			name='Existing Facility',
			facility_type='clinic',
			registration_number='REG-EXISTING-002',
			email='hello@sunrise.test',
			phone='0700000002',
		)
		self.client.force_authenticate(user=admin)

		response = self.client.post(
			reverse('facility-list'),
			{
				'name': 'Different Facility',
				'facility_type': 'clinic',
				'registration_number': 'REG-2026-004',
				'email': 'HELLO@SUNRISE.TEST',
				'phone': '0733333333',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(
			response.data['email'][0],
			'A facility with this email already exists.'
		)

	def test_create_facility_rejects_duplicate_registration_number(self):
		admin = User.objects.create_user(
			username='duplicate_registration_admin',
			email='duplicate-registration-admin@example.com',
			password='StrongPass123!',
			role='admin',
		)
		Facility.objects.create(
			name='Registration Existing Facility',
			facility_type='clinic',
			registration_number='REG-EXISTING-003',
			email='existing-registration@example.com',
			phone='0700000003',
		)
		self.client.force_authenticate(user=admin)

		response = self.client.post(
			reverse('facility-list'),
			{
				'name': 'Another Facility',
				'facility_type': 'clinic',
				'registration_number': 'REG-EXISTING-003',
				'email': 'another-registration@example.com',
				'phone': '0744444444',
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertEqual(
			response.data['registration_number'][0],
			'A facility with this registration number already exists.'
		)

	def test_create_user_requires_request_user_facility(self):
		user = User.objects.create_user(
			username='admin_without_facility',
			email='admin@example.com',
			password='StrongPass123!',
			role='staff',
		)
		self.client.force_authenticate(user=user)

		response = self.client.post(
			reverse('user-list'),
			{
				'username': 'doctor1',
				'email': 'doctor1@example.com',
				'first_name': 'Doc',
				'last_name': 'Tor',
				'role': 'doctor',
				'phone': '0708320123',
				'department': 'Dentist',
				'is_active': True,
				'is_verified': True,
			},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(
			response.data['detail'],
			'Your account is not assigned to a facility.'
		)
