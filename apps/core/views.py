# apps/core/views.py

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from datetime import timedelta
import uuid
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from .models import User, Facility, Department, FacilityOnboarding, AuditLog, EmailOTP, FacilityRole, FacilitySubscriptionPayment, ALL_MODULE_PERMISSIONS
from .utils import generate_and_send_otp
from .serializers import (
    SignupSerializer, LoginSerializer, SignupResponseSerializer,
    LoginResponseSerializer, UserSerializer, UserDetailSerializer,
    FacilityListSerializer, FacilityDetailSerializer, FacilityWriteSerializer,
    FacilityUpdateSerializer, FacilitySubscriptionPaymentSerializer, SubscribePackageSerializer,
    DepartmentSerializer, VerifyOTPSerializer, ResendOTPSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    FacilityRoleSerializer,
)


def get_audit_facility_for_user(user):
    """
    Resolve a facility for audit logs when possible.
    Some admin users may not belong to a facility.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    if getattr(user, 'facility_id', None):
        return user.facility

    if getattr(user, 'role', None) == 'admin':
        return Facility.objects.order_by('id').first()

    return None


class PasswordResetRequestView(APIView):
    """Send a one-time password-reset link to a user's registered email."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Always return the same response so this endpoint cannot be used to
        # discover which email addresses have an account.
        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_base_url = getattr(
                settings,
                'PASSWORD_RESET_URL',
                'https://afyorahms.vercel.app/reset-password',
            ).rstrip('/')
            reset_url = f'{reset_base_url}?uid={uid}&token={token}'

            message = (
                f'Hello {user.get_full_name() or user.username},\n\n'
                'We received a request to reset your Afyora HMS password.\n\n'
                f'Reset your password: {reset_url}\n\n'
                'If you did not request this, you can safely ignore this email.'
            )
            email_message = EmailMultiAlternatives(
                subject='Afyora HMS — Reset your password',
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            email_message.send(fail_silently=False)

        return Response(
            {'message': 'If an active account exists for this email, a password-reset link has been sent.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """Set a new password after a valid password-reset link is presented."""

    permission_classes = [AllowAny]

    def post(self, request, uid, token):
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'error': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({'error': 'Invalid or expired reset link.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PasswordResetConfirmSerializer(data=request.data, context={'user': user})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password', 'updated_at'])

        return Response({'message': 'Password reset successfully. You can now log in.'})


# ============================================================================
# CONCEPTS EXPLANATION
# ============================================================================
# 
# APIView: Basic view - control everything yourself
# ViewSet: Advanced view - combines CRUD (Create, Read, Update, Delete)
#
# Example ViewSet automatically provides:
# - GET /users/ → list all users (list action)
# - GET /users/1/ → get user #1 (retrieve action)
# - POST /users/ → create new user (create action)
# - PUT /users/1/ → update user #1 (update action)
# - DELETE /users/1/ → delete user #1 (destroy action)
#
# Status Codes:
# - 200: Success (GET, PUT)
# - 201: Created (POST)
# - 400: Bad request (validation error)
# - 401: Unauthorized (no token)
# - 403: Forbidden (don't have permission)
# - 404: Not found
# - 500: Server error


# ============================================================================
# SIGNUP VIEW
# ============================================================================

class SignupView(APIView):
    """
    POST /api/auth/signup/
    
    Register a new facility and its admin user.
    
    Request body:
    {
        "facility_type": "hospital",
        "facility_name": "Nairobi Hospital",
        "registration_number": "REG/2024/001",
        "admin_first_name": "John",
        "admin_last_name": "Doe",
        "email": "john@hospital.com",
        "phone": "+254712345678",
        "password": "SecurePass123!",
    }
    
    Response:
    {
        "organization_id": 1,
        "onboarding_required": true,
        "message": "Signup successful. Please complete onboarding."
    }
    """
    
    # AllowAny means anyone can access this (no login required)
    permission_classes = [AllowAny]

    @staticmethod
    def _normalize_signup_payload(payload):
        """Support both snake_case and camelCase request formats."""
        data = payload.copy()
        alias_map = {
            'facilityType': 'facility_type',
            'facilityName': 'facility_name',
            'registrationNumber': 'registration_number',
            'adminFirstName': 'admin_first_name',
            'adminLastName': 'admin_last_name',
            'passwordConfirm': 'password_confirm',
        }

        for source_key, target_key in alias_map.items():
            if source_key in data and target_key not in data:
                data[target_key] = data[source_key]

        if 'password' in data and 'password_confirm' not in data:
            data['password_confirm'] = data['password']

        return data
    
    def post(self, request):
        """Handle signup request"""

        normalized_data = self._normalize_signup_payload(request.data)

        # Initialize serializer with data from request
        serializer = SignupSerializer(data=normalized_data)
        
        # Validate all the data
        if not serializer.is_valid():
            # If validation fails, return errors
            # Status 400 = Bad Request
            return Response(
                {
                    'error': 'Validation failed',
                    'details': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If validation passes, save to database
        # This calls SignupSerializer.create()
        try:
            with transaction.atomic():
                # transaction.atomic() ensures all-or-nothing:
                # If anything fails, database changes are rolled back
                facility = serializer.save()

                # Log this signup action
                AuditLog.objects.create(
                    facility=facility,
                    action='create',
                    model_name='Facility',
                    object_id=str(facility.id),
                    description=f'New facility registered: {facility.name}'
                )

            # Send email OTP after transaction successfully commits
            admin_user = facility.users.filter(role='facility_admin').first()
            if admin_user:
                generate_and_send_otp(admin_user)

            # Build response
            response_data = {
                'organization_id': facility.id,
                'onboarding_required': True,
                'is_verified': False,
                'message': 'Signup successful! A 6-digit verification code has been sent to your email.'
            }

            # Status 201 = Created (standard for POST that creates resource)
            return Response(
                response_data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            # If something goes wrong during creation
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# LOGIN VIEW
# ============================================================================

class LoginView(APIView):
    """
    POST /api/auth/login/
    
    Authenticate user and return access token.
    
    Request body:
    {
        "email": "john@hospital.com",
        "password": "SecurePass123!",
        "remember_me": true
    }
    
    Response:
    {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
        "user": {
            "id": 1,
            "email": "john@hospital.com",
            "role": "facility_admin",
            ...
        }
    }
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle login request"""
        
        # Validate credentials
        serializer = LoginSerializer(data=request.data)
        
        if not serializer.is_valid():
            # Login failed (invalid email/password, account inactive, etc.)
            return Response(
                {
                    'error': 'Login failed',
                    'details': serializer.errors
                },
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get authenticated user
        user = serializer.validated_data['user']

        if serializer.validated_data.get('require_password_change'):
            return Response(
                {
                    'require_password_change': True,
                    'first_login': True,
                    'email': user.email,
                    'message': 'First time login detected. Please update your password to proceed.',
                },
                status=status.HTTP_200_OK,
            )

        if serializer.validated_data.get('perform_password_change'):
            new_password = serializer.validated_data.get('new_password')
            user.set_password(new_password)
            user.must_change_password = False
            user.save(update_fields=['password', 'must_change_password', 'updated_at'])
        
        # Generate JWT tokens
        # JWT = JSON Web Token (stateless authentication)
        # Access token: Short-lived, used for API requests
        # Refresh token: Long-lived, used to get new access token
        refresh = RefreshToken.for_user(user)
        
        # Update last login info
        user.last_login_ip = self.request.META.get('REMOTE_ADDR')
        user.last_login_device = request.META.get('HTTP_USER_AGENT', '')[:100]
        user.save()

        audit_facility = get_audit_facility_for_user(user)
        
        # Log login action
        if audit_facility is not None:
            AuditLog.objects.create(
                facility=audit_facility,
                user=user,
                action='login',
                model_name='User',
                object_id=str(user.id),
                description=f'{user.get_full_name()} logged in',
                ip_address=self.request.META.get('REMOTE_ADDR')
            )
        
        # Build response
        response_data = {
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': UserSerializer(user).data,
            'message': 'Login successful'
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


class RefreshView(APIView):
    """
    POST /api/auth/refresh or /api/auth/refresh/

    Refreshes JWT access token and (optionally) rotates refresh token.
    Accepts both `refresh` and frontend camelCase `refreshToken` keys.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        incoming_refresh = (
            request.data.get('refresh')
            or request.data.get('refresh_token')
            or request.data.get('refreshToken')
        )

        if not incoming_refresh:
            return Response(
                {
                    'error': 'Validation failed',
                    'details': {'refresh': ['This field is required.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TokenRefreshSerializer(data={'refresh': incoming_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            # A token signed by an old key (for example after a deployment),
            # expired token, or malformed token is an authentication failure,
            # never an unhandled server error.
            return Response(
                {'error': 'Invalid or expired refresh token. Please sign in again.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token_data = serializer.validated_data
        response_data = {'access_token': token_data.get('access')}

        # Only present when token rotation is enabled.
        if token_data.get('refresh'):
            response_data['refresh_token'] = token_data['refresh']

        return Response(response_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Stateless logout endpoint for frontend coordination and audit logging.
    Clients should clear access/refresh tokens after this call.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        audit_facility = get_audit_facility_for_user(user)

        if audit_facility is not None:
            AuditLog.objects.create(
                facility=audit_facility,
                user=user,
                action='login',
                model_name='User',
                object_id=str(user.id),
                description=f'{user.get_full_name()} logged out',
                ip_address=self.request.META.get('REMOTE_ADDR')
            )

        return Response(
            {'message': 'Logout successful'},
            status=status.HTTP_200_OK
        )


class CompleteOnboardingView(APIView):
    """
    POST /api/auth/onboarding/complete/

    Completes facility onboarding after signup.
    Accepts camelCase fields from the frontend and persists core records.
    """

    permission_classes = [AllowAny]

    @staticmethod
    def _normalize_payload(payload):
        data = payload.copy()
        alias_map = {
            'organizationId': 'organization_id',
            'facilityName': 'facility_name',
            'facilityEmail': 'facility_email',
            'licenseNumber': 'license_number',
            'numberOfBeds': 'number_of_beds',
            'adminFirstName': 'admin_first_name',
            'adminLastName': 'admin_last_name',
            'adminEmail': 'admin_email',
            'adminPassword': 'admin_password',
            'adminConfirmPassword': 'admin_confirm_password',
            'selectedPlan': 'selected_plan',
        }

        for source_key, target_key in alias_map.items():
            if source_key in data and target_key not in data:
                data[target_key] = data[source_key]

        if 'admin_password' in data and 'admin_confirm_password' not in data:
            data['admin_confirm_password'] = data['admin_password']

        return data

    def post(self, request):
        payload = self._normalize_payload(request.data)

        required_fields = [
            'organization_id', 'facility_name', 'address', 'city', 'phone',
            'facility_email', 'license_number', 'admin_first_name',
            'admin_last_name', 'admin_email', 'admin_password',
            'admin_confirm_password', 'selected_plan'
        ]

        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            return Response(
                {
                    'error': 'Validation failed',
                    'details': {field: ['This field is required.'] for field in missing}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if payload['admin_password'] != payload['admin_confirm_password']:
            return Response(
                {
                    'error': 'Validation failed',
                    'details': {
                        'admin_confirm_password': ['Passwords do not match.']
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            organization_id = int(payload['organization_id'])
        except (TypeError, ValueError):
            return Response(
                {
                    'error': 'Validation failed',
                    'details': {
                        'organization_id': ['A valid organization ID is required.']
                    }
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            facility = Facility.objects.get(id=organization_id)
        except Facility.DoesNotExist:
            return Response(
                {
                    'error': 'Validation failed',
                    'details': {
                        'organization_id': ['Facility not found.']
                    }
                },
                status=status.HTTP_404_NOT_FOUND
            )

        admin_user = facility.users.filter(role='facility_admin').first()
        if admin_user and not admin_user.is_verified:
            return Response(
                {
                    'error': 'Email not verified',
                    'message': 'Please verify your email address via OTP before completing onboarding.',
                    'is_verified': False
                },
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            facility.name = payload['facility_name']
            facility.address = payload['address']
            facility.city = payload['city']
            facility.phone = payload['phone']
            facility.email = payload['facility_email']
            facility.registration_number = payload['license_number']
            facility.onboarding_completed = True
            facility.save()

            admin_user = facility.users.filter(role='facility_admin').first()
            if admin_user is None:
                return Response(
                    {
                        'error': 'Validation failed',
                        'details': {
                            'admin_email': ['Facility admin user was not found.']
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            admin_user.first_name = payload['admin_first_name']
            admin_user.last_name = payload['admin_last_name']
            admin_user.email = payload['admin_email']
            admin_user.phone = payload['phone']
            admin_user.license_number = payload['license_number']
            admin_user.specialization = payload.get('specialization', '')
            admin_user.set_password(payload['admin_password'])
            admin_user.save()

            onboarding, _ = FacilityOnboarding.objects.get_or_create(facility=facility)
            onboarding.basic_info_completed = True
            onboarding.staff_added = True
            onboarding.departments_configured = True
            onboarding.settings_configured = True
            onboarding.check_completion()

            modules_payload = payload.get('modules') or {}
            selected_modules_count = 0
            if isinstance(modules_payload, dict):
                selected_modules_count = sum(1 for value in modules_payload.values() if value)
            elif isinstance(modules_payload, list):
                selected_modules_count = len(modules_payload)

            AuditLog.objects.create(
                facility=facility,
                user=admin_user,
                action='update',
                model_name='FacilityOnboarding',
                object_id=str(facility.id),
                description=(
                    f"Onboarding completed for {facility.name}. "
                    f"Plan: {payload.get('selected_plan')}. "
                    f"Modules selected: {selected_modules_count}."
                )
            )

        return Response(
            {
                'organization_id': facility.id,
                'onboarding_completed': True,
                'message': 'Facility onboarding completed successfully.'
            },
            status=status.HTTP_200_OK
        )


# ============================================================================
# VERIFY OTP VIEW
# ============================================================================

class VerifyOTPView(APIView):
    """
    POST /api/auth/verify-otp/

    Verify 6-digit OTP code sent to user email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'error': 'Validation failed',
                    'details': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {
                    'error': 'User not found',
                    'details': {'email': ['No account found with this email address.']}
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if user.is_verified:
            return Response(
                {
                    'message': 'Email address is already verified.',
                    'is_verified': True
                },
                status=status.HTTP_200_OK
            )

        # Look for matching OTP code
        otp_instance = EmailOTP.objects.filter(
            user=user,
            code=otp_code,
            is_used=False
        ).order_by('-created_at').first()

        if not otp_instance or not otp_instance.is_valid():
            return Response(
                {
                    'error': 'Invalid or expired OTP code',
                    'details': {'otp': ['The verification code is invalid or has expired. Please request a new code.']}
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            otp_instance.is_used = True
            otp_instance.save(update_fields=['is_used', 'updated_at'])

            user.is_verified = True
            user.save(update_fields=['is_verified', 'updated_at'])

        return Response(
            {
                'message': 'Email verified successfully.',
                'is_verified': True
            },
            status=status.HTTP_200_OK
        )


# ============================================================================
# RESEND OTP VIEW
# ============================================================================

class ResendOTPView(APIView):
    """
    POST /api/auth/resend-otp/

    Triggers resend of 6-digit OTP code to user email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'error': 'Validation failed',
                    'details': serializer.errors
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {
                    'error': 'User not found',
                    'details': {'email': ['No account found with this email address.']}
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if user.is_verified:
            return Response(
                {
                    'message': 'Email address is already verified.',
                    'is_verified': True
                },
                status=status.HTTP_200_OK
            )

        generate_and_send_otp(user, email=user.email)

        return Response(
            {
                'message': 'A new 6-digit verification code has been sent to your email.',
                'email': user.email
            },
            status=status.HTTP_200_OK
        )


# ============================================================================
# USER VIEWSET
# ============================================================================

class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoints for user management.
    
    Endpoints:
    - GET /api/users/ → List users
    - POST /api/users/ → Create user
    - GET /api/users/{id}/ → Get user details
    - PUT /api/users/{id}/ → Update user
    - DELETE /api/users/{id}/ → Delete user
    
    Custom endpoints:
    - GET /api/users/{id}/profile/ → Get own profile
    - PATCH /api/users/{id}/change-password/ → Change password
    - GET /api/users/facility/staff/ → List facility staff
    """
    
    # Only authenticated users can access
    permission_classes = [IsAuthenticated]
    
    # Allow filtering by role, department, etc.
    filterset_fields = ['role', 'department', 'is_active']
    
    # Allow searching by name, email
    search_fields = ['first_name', 'last_name', 'email']
    
    # Default ordering
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Users only see users in their facility.
        This is CRITICAL for multi-tenancy security.
        
        If not done, User A could see User B's data from different facility!
        """
        user = self.request.user
        
        if user.role == 'admin':
            # Super admin sees all users
            return User.objects.all()
        
        if user.facility:
            # Facility users only see their facility's users
            return user.facility.users.all()
        
        # Shouldn't happen, but return empty queryset
        return User.objects.none()
    
    def get_serializer_class(self):
        """
        Use different serializers for different actions.
        
        - list: Compact info
        - retrieve: Detailed info
        - create/update: Full form
        """
        if self.action == 'retrieve':
            return UserDetailSerializer
        return UserSerializer
    
    def perform_create(self, serializer):
        """
        Called when creating a new user.
        Adds facility context automatically.
        """
        facility = self.request.user.facility
        if facility is None:
            raise PermissionDenied('Your account is not assigned to a facility.')

        user = serializer.save(
            facility=facility
            # Automatically assign to same facility as requester
        )
        
        # Log user creation
        AuditLog.objects.create(
            facility=facility,
            user=self.request.user,
            action='create',
            model_name='User',
            object_id=str(user.id),
            description=f'User created: {user.get_full_name()}'
        )
    
    def perform_update(self, serializer):
        """Log user updates"""
        serializer.save()
        
        AuditLog.objects.create(
            facility=self.request.user.facility,
            user=self.request.user,
            action='update',
            model_name='User',
            object_id=str(serializer.instance.id),
            description=f'User updated: {serializer.instance.get_full_name()}'
        )
    
    def perform_destroy(self, instance):
        """
        Don't actually delete users, just deactivate.
        This preserves historical data and audit trail.
        """
        instance.is_active = False
        instance.save()
        
        AuditLog.objects.create(
            facility=instance.facility,
            user=self.request.user,
            action='delete',
            model_name='User',
            object_id=str(instance.id),
            description=f'User deactivated: {instance.get_full_name()}'
        )
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        GET /api/users/profile/
        Get current logged-in user's profile
        """
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        """
        POST /api/users/{id}/change-password/
        
        Request body:
        {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "confirm_password": "NewPass456!"
        }
        """
        user = self.get_object()
        
        # Only users/admins can change their own password
        if request.user != user and request.user.role != 'admin':
            return Response(
                {'error': 'You cannot change another user\'s password'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        # Validate
        if not user.check_password(old_password):
            return Response(
                {'error': 'Old password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(new_password) < 12:
            return Response(
                {'error': 'Password must be at least 12 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        AuditLog.objects.create(
            facility=user.facility,
            user=request.user,
            action='update',
            model_name='User',
            object_id=str(user.id),
            description=f'Password changed for {user.get_full_name()}'
        )
        
        return Response(
            {'message': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['get'])
    def staff(self, request):
        """
        GET /api/users/staff/
        Get all staff members in this facility
        """
        users = self.get_queryset().filter(
            role__in=['doctor', 'nurse', 'pharmacist', 'lab_technician']
        )
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


# ============================================================================
# FACILITY VIEWSET
# ============================================================================

class FacilityViewSet(viewsets.ModelViewSet):
    """
    Facility viewset for managing facility details, profile updates, and subscriptions.
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']
    filterset_fields = ['facility_type', 'subscription_active', 'subscription_package']
    search_fields = ['name', 'city', 'email']
    ordering = ['-created_at']

    # Pricing map in KES (Kenya Shillings)
    PACKAGE_PRICING = {
        'basic': {'monthly': 2999.00, 'yearly': 28790.00},
        'professional': {'monthly': 5999.00, 'yearly': 57590.00},
        'enterprise': {'monthly': 12999.00, 'yearly': 124790.00},
    }
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return Facility.objects.all()
        if user.facility:
            return Facility.objects.filter(id=user.facility.id)
        return Facility.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FacilityWriteSerializer
        if self.action in ['update', 'partial_update']:
            return FacilityUpdateSerializer
        if self.action == 'retrieve':
            return FacilityDetailSerializer
        return FacilityListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        detail_serializer = FacilityDetailSerializer(
            serializer.instance,
            context=self.get_serializer_context()
        )
        headers = self.get_success_headers(detail_serializer.data)
        return Response(
            detail_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )

    def perform_create(self, serializer):
        if self.request.user.role != 'admin':
            raise PermissionDenied('Only administrators can create facilities.')

        with transaction.atomic():
            facility = serializer.save()
            FacilityOnboarding.objects.create(facility=facility)
            AuditLog.objects.create(
                facility=facility,
                user=self.request.user,
                action='create',
                model_name='Facility',
                object_id=str(facility.id),
                description=f'Facility created: {facility.name}'
            )

    def perform_update(self, serializer):
        facility = self.get_object()
        user = self.request.user
        if user.role != 'admin' and (not user.facility or user.facility.id != facility.id):
            raise PermissionDenied('You do not have permission to update this facility profile.')
        
        with transaction.atomic():
            updated_facility = serializer.save()
            AuditLog.objects.create(
                facility=updated_facility,
                user=user,
                action='update',
                model_name='Facility',
                object_id=str(updated_facility.id),
                description=f'Facility profile updated: {updated_facility.name}'
            )

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='my-facility')
    def my_facility(self, request):
        """Shortcut endpoint to fetch or update current user's facility profile."""
        if not request.user.facility:
            return Response({'detail': 'User is not associated with any facility.'}, status=status.HTTP_404_NOT_FOUND)
        
        facility = request.user.facility
        if request.method == 'GET':
            serializer = FacilityDetailSerializer(facility, context={'request': request})
            return Response(serializer.data)
        
        # PUT or PATCH
        serializer = FacilityUpdateSerializer(
            facility,
            data=request.data,
            partial=(request.method == 'PATCH'),
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        AuditLog.objects.create(
            facility=facility,
            user=request.user,
            action='update',
            model_name='Facility',
            object_id=str(facility.id),
            description=f'Facility profile updated: {facility.name}'
        )
        detail_serializer = FacilityDetailSerializer(facility, context={'request': request})
        return Response(detail_serializer.data)

    @action(detail=True, methods=['post'], url_path='subscribe')
    def subscribe(self, request, pk=None):
        """Process package upgrade and subscription payment."""
        facility = self.get_object()
        user = request.user

        if user.role != 'admin' and (not user.facility or user.facility.id != facility.id):
            raise PermissionDenied('You can only upgrade subscriptions for your own facility.')

        serializer = SubscribePackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        package = data['package']
        billing_cycle = data.get('billing_cycle', 'monthly')
        payment_method = data.get('payment_method', 'mpesa')
        phone_number = data.get('phone_number', '')

        # Calculate pricing
        pricing = self.PACKAGE_PRICING.get(package, {'monthly': 15000.00, 'yearly': 144000.00})
        amount = pricing.get(billing_cycle, pricing['monthly'])

        # Generate unique transaction reference
        txn_ref = f"SUB-PAY-{uuid.uuid4().hex[:8].upper()}"

        with transaction.atomic():
            # Record payment history
            payment = FacilitySubscriptionPayment.objects.create(
                facility=facility,
                package=package,
                billing_cycle=billing_cycle,
                amount=amount,
                payment_method=payment_method,
                phone_number=phone_number,
                transaction_reference=txn_ref,
                status='completed',
                notes=f"Subscription upgrade to {package.title()} ({billing_cycle})"
            )

            # Update facility subscription state
            today = timezone.now().date()
            days_to_add = 365 if billing_cycle == 'yearly' else 30
            new_end_date = today + timedelta(days=days_to_add)

            facility.subscription_package = package
            facility.subscription_billing_cycle = billing_cycle
            facility.subscription_active = True
            facility.subscription_start_date = today
            facility.subscription_end_date = new_end_date
            facility.save()

            AuditLog.objects.create(
                facility=facility,
                user=user,
                action='update',
                model_name='Facility',
                object_id=str(facility.id),
                description=f'Upgraded subscription package to {package} ({billing_cycle}), Txn: {txn_ref}'
            )

        facility_data = FacilityDetailSerializer(facility, context={'request': request}).data
        payment_data = FacilitySubscriptionPaymentSerializer(payment).data

        return Response({
            'message': f'Successfully subscribed to {package.title()} plan!',
            'facility': facility_data,
            'payment': payment_data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='subscription-history')
    def subscription_history(self, request, pk=None):
        """Retrieve list of subscription payments for this facility."""
        facility = self.get_object()
        user = request.user

        if user.role != 'admin' and (not user.facility or user.facility.id != facility.id):
            raise PermissionDenied('You can only view subscription history for your own facility.')

        payments = facility.subscription_payments.all()
        serializer = FacilitySubscriptionPaymentSerializer(payments, many=True)
        return Response(serializer.data)


# ============================================================================
# DEPARTMENT VIEWSET
# ============================================================================

class DepartmentViewSet(viewsets.ModelViewSet):
    """
    Manage departments within a facility.
    
    Endpoints:
    - GET /api/departments/ → List facility departments
    - POST /api/departments/ → Create department
    - GET /api/departments/{id}/ → Get department details
    - PUT /api/departments/{id}/ → Update department
    - DELETE /api/departments/{id}/ → Delete department
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = DepartmentSerializer
    filterset_fields = ['is_operational']
    search_fields = ['name']
    ordering = ['name']
    
    def get_queryset(self):
        """Only see departments in own facility"""
        if self.request.user.facility:
            return self.request.user.facility.departments.all()
        return Department.objects.none()
    
    def perform_create(self, serializer):
        """Auto-assign to user's facility"""
        facility = self.request.user.facility
        if facility is None:
            raise PermissionDenied('Your account is not assigned to a facility.')

        serializer.save(facility=facility)
        
        AuditLog.objects.create(
            facility=facility,
            user=self.request.user,
            action='create',
            model_name='Department',
            object_id=str(serializer.instance.id),
            description=f'Department created: {serializer.instance.name}'
        )


# ============================================================================
# FACILITY ROLE VIEWSET (Dynamic RBAC)
# ============================================================================

class FacilityRoleViewSet(viewsets.ModelViewSet):
    """
    CRUD for custom roles scoped to the logged-in facility.

    Endpoints:
    - GET  /api/roles/          → list roles (all authenticated)
    - POST /api/roles/          → create role (facility_admin only)
    - GET  /api/roles/{id}/     → retrieve role
    - PUT  /api/roles/{id}/     → update role (facility_admin only)
    - PATCH /api/roles/{id}/    → partial update role (facility_admin only)
    - DELETE /api/roles/{id}/   → delete role (facility_admin only)

    Custom endpoints:
    - GET  /api/roles/modules/         → list all available permission module keys
    - POST /api/roles/{id}/assign/     → assign this role to a user
    """

    permission_classes = [IsAuthenticated]
    serializer_class = FacilityRoleSerializer
    search_fields = ['name', 'description']
    ordering = ['name']

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            facility_id = self.request.query_params.get('facility_id')
            if facility_id:
                return FacilityRole.objects.filter(facility_id=facility_id)
            return FacilityRole.objects.all()
        if user.facility:
            return FacilityRole.objects.filter(facility=user.facility)
        return FacilityRole.objects.none()

    def _require_facility_admin(self):
        user = self.request.user
        if user.role not in ('admin', 'facility_admin'):
            raise PermissionDenied('Only facility administrators can manage roles.')

    def perform_create(self, serializer):
        self._require_facility_admin()
        facility = self.request.user.facility
        if facility is None:
            raise PermissionDenied('Your account is not assigned to a facility.')
        role = serializer.save(facility=facility)
        AuditLog.objects.create(
            facility=facility,
            user=self.request.user,
            action='create',
            model_name='FacilityRole',
            object_id=str(role.id),
            description=f'Role created: {role.name}',
        )

    def perform_update(self, serializer):
        self._require_facility_admin()
        role = serializer.save()
        AuditLog.objects.create(
            facility=self.request.user.facility,
            user=self.request.user,
            action='update',
            model_name='FacilityRole',
            object_id=str(role.id),
            description=f'Role updated: {role.name}',
        )

    def perform_destroy(self, instance):
        self._require_facility_admin()
        facility = self.request.user.facility
        role_name = instance.name
        # Unlink all users and employees before deletion
        instance.users.all().update(custom_role=None)
        instance.employees.all().update(custom_role=None)
        instance.delete()
        AuditLog.objects.create(
            facility=facility,
            user=self.request.user,
            action='delete',
            model_name='FacilityRole',
            object_id='deleted',
            description=f'Role deleted: {role_name}',
        )

    @action(detail=False, methods=['get'], url_path='modules')
    def modules(self, request):
        """GET /api/roles/modules/ — return all available permission module keys."""
        return Response({'modules': ALL_MODULE_PERMISSIONS})

    @action(detail=True, methods=['post'], url_path='assign')
    def assign(self, request, pk=None):
        """
        POST /api/roles/{id}/assign/
        Assign this role to a user or employee.

        Body: { "user_id": 5 }  OR  { "employee_id": "EMP001" }
        """
        self._require_facility_admin()
        role = self.get_object()
        facility = self.request.user.facility

        user_id = request.data.get('user_id')
        employee_id = request.data.get('employee_id')

        if not user_id and not employee_id:
            return Response(
                {'error': 'Provide either user_id or employee_id.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = []

        if user_id:
            try:
                target_user = User.objects.get(id=user_id, facility=facility)
                target_user.custom_role = role
                target_user.save(update_fields=['custom_role', 'updated_at'])
                updated.append(f'user:{user_id}')
                AuditLog.objects.create(
                    facility=facility,
                    user=request.user,
                    action='update',
                    model_name='User',
                    object_id=str(user_id),
                    description=f'Custom role "{role.name}" assigned to user {user_id}.',
                )
            except User.DoesNotExist:
                return Response(
                    {'error': f'User {user_id} not found in your facility.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if employee_id:
            # Import here to avoid circular import
            from employees.models import Employee
            try:
                emp = Employee.objects.get(employee_id=employee_id, facility=facility)
                emp.custom_role = role
                emp.save(update_fields=['custom_role', 'updated_at'])
                # Also update the linked user account if it exists
                linked_user = User.objects.filter(
                    email=emp.email, facility=facility
                ).first()
                if linked_user:
                    linked_user.custom_role = role
                    linked_user.save(update_fields=['custom_role', 'updated_at'])
                updated.append(f'employee:{employee_id}')
                AuditLog.objects.create(
                    facility=facility,
                    user=request.user,
                    action='update',
                    model_name='Employee',
                    object_id=employee_id,
                    description=f'Custom role "{role.name}" assigned to employee {employee_id}.',
                )
            except Employee.DoesNotExist:
                return Response(
                    {'error': f'Employee {employee_id} not found in your facility.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {
                'message': f'Role "{role.name}" assigned successfully.',
                'updated': updated,
                'role': FacilityRoleSerializer(role).data,
            },
            status=status.HTTP_200_OK,
        )
