from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Facility, FacilityOnboarding, User


class TransactionalEmailTests(TestCase):
	@override_settings(
		BREVO_API_KEY='brevo_test_key',
		BREVO_API_URL='https://email-provider.test/v3/smtp/email',
		BREVO_TIMEOUT=7,
		DEFAULT_FROM_EMAIL='Afyora HMS <verified@afyora.example>',
	)
	def test_brevo_api_payload_is_used_for_transactional_email(self):
		from unittest.mock import Mock, patch
		from .utils import send_transactional_email

		response = Mock()
		response.ok = True
		response.json.return_value = {'messageId': 'email_123'}
		with patch('core.utils.requests.post', return_value=response) as post:
			message_id = send_transactional_email(
				to_email='patient@example.com',
				subject='Verification code',
				text='Your code is 123456',
				html='<p>Your code is 123456</p>',
			)

		self.assertEqual(message_id, 'email_123')
		post.assert_called_once_with(
			'https://email-provider.test/v3/smtp/email',
			headers={
				'api-key': 'brevo_test_key',
				'Content-Type': 'application/json',
				'Accept': 'application/json',
			},
			json={
				'sender': {'name': 'Afyora HMS', 'email': 'verified@afyora.example'},
				'to': [{'email': 'patient@example.com'}],
				'subject': 'Verification code',
				'textContent': 'Your code is 123456',
				'htmlContent': '<p>Your code is 123456</p>',
			},
			timeout=7,
		)

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

	def test_refresh_accepts_camel_case_refresh_token(self):
		user = User.objects.create_user(
			username='refresh_user',
			email='refresh-user@example.com',
			password='StrongPass123!',
			role='staff',
		)
		refresh = RefreshToken.for_user(user)

		response = self.client.post(
			reverse('refresh'),
			{'refreshToken': str(refresh)},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('access_token', response.data)

	def test_refresh_works_without_trailing_slash(self):
		user = User.objects.create_user(
			username='refresh_no_slash_user',
			email='refresh-no-slash@example.com',
			password='StrongPass123!',
			role='staff',
		)
		refresh = RefreshToken.for_user(user)

		response = self.client.post(
			'/api/auth/refresh',
			{'refreshToken': str(refresh)},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('access_token', response.data)

	def test_refresh_rejects_invalid_token_without_server_error(self):
		response = self.client.post(
			reverse('refresh'),
			{'refreshToken': 'not-a-valid-token'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


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


class EmailOTPVerificationTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_signup_sends_otp_and_unverified_onboarding_is_blocked(self):
		signup_payload = {
			'facilityType': 'clinic',
			'facilityName': 'Test Wellness Clinic',
			'registrationNumber': 'REG-OTP-1001',
			'adminFirstName': 'Alice',
			'adminLastName': 'Smith',
			'email': 'alice@testwellness.com',
			'phone': '+254711223344',
			'password': 'SecurePassword123!',
		}

		# 1. Trigger Signup
		response = self.client.post(reverse('signup'), signup_payload, format='json')
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		organization_id = response.data['organization_id']

		user = User.objects.get(email='alice@testwellness.com')
		self.assertFalse(user.is_verified)

		# Verify OTP record created
		from .models import EmailOTP
		otp = EmailOTP.objects.filter(user=user, is_used=False).first()
		self.assertIsNotNone(otp)
		self.assertEqual(len(otp.code), 6)

		# 2. Attempt onboarding before verification -> blocked (403)
		onboarding_payload = {
			'organizationId': organization_id,
			'facilityName': 'Test Wellness Clinic Updated',
			'facilityEmail': 'info@testwellness.com',
			'address': '123 Health Way',
			'city': 'Nairobi',
			'phone': '+254711223344',
			'licenseNumber': 'REG-OTP-1001',
			'adminFirstName': 'Alice',
			'adminLastName': 'Smith',
			'adminEmail': 'alice@testwellness.com',
			'adminPassword': 'SecurePassword123!',
			'selectedPlan': 'basic',
		}
		onboarding_response = self.client.post(
			reverse('complete-onboarding'),
			onboarding_payload,
			format='json'
		)
		self.assertEqual(onboarding_response.status_code, status.HTTP_403_FORBIDDEN)
		self.assertEqual(onboarding_response.data['error'], 'Email not verified')

		# 3. Verify OTP with incorrect code -> 400 Bad Request
		invalid_verify = self.client.post(
			reverse('verify-otp'),
			{'email': 'alice@testwellness.com', 'otp': '000000'},
			format='json'
		)
		self.assertEqual(invalid_verify.status_code, status.HTTP_400_BAD_REQUEST)

		# 4. Trigger resend OTP
		resend_response = self.client.post(
			reverse('resend-otp'),
			{'email': 'alice@testwellness.com'},
			format='json'
		)
		self.assertEqual(resend_response.status_code, status.HTTP_200_OK)

		new_otp = EmailOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
		self.assertIsNotNone(new_otp)

		# 5. Verify OTP with valid code -> 200 OK
		valid_verify = self.client.post(
			reverse('verify-otp'),
			{'email': 'alice@testwellness.com', 'otp': new_otp.code},
			format='json'
		)
		self.assertEqual(valid_verify.status_code, status.HTTP_200_OK)
		user.refresh_from_db()
		self.assertTrue(user.is_verified)

		# 6. Now onboarding completion succeeds
		success_onboarding = self.client.post(
			reverse('complete-onboarding'),
			onboarding_payload,
			format='json'
		)
		self.assertEqual(success_onboarding.status_code, status.HTTP_200_OK)
		self.assertTrue(success_onboarding.data['onboarding_completed'])
