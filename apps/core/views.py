# apps/core/views.py

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db import transaction
from .models import User, Facility, Department, FacilityOnboarding, AuditLog
from .serializers import (
    SignupSerializer, LoginSerializer, SignupResponseSerializer,
    LoginResponseSerializer, UserSerializer, UserDetailSerializer,
    FacilityListSerializer, FacilityDetailSerializer, FacilityWriteSerializer,
    DepartmentSerializer
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
                
                # Build response
                response_data = {
                    'organization_id': facility.id,
                    'onboarding_required': True,
                    'message': 'Signup successful! Please complete onboarding.'
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
    Facility viewset for listing, retrieving, and creating facilities.
    
    Endpoints:
    - POST /api/facilities/ → Create facility (admin only)
    - GET /api/facilities/ → List facilities (admin only)
    - GET /api/facilities/{id}/ → Get facility details
    """
    
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']
    filterset_fields = ['facility_type', 'subscription_active']
    search_fields = ['name', 'city', 'email']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """
        Admin sees all facilities.
        Regular users only see their own facility.
        """
        user = self.request.user
        
        if user.role == 'admin':
            return Facility.objects.all()
        
        if user.facility:
            return Facility.objects.filter(id=user.facility.id)
        
        return Facility.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return FacilityWriteSerializer
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
        """Only system admins can create facilities directly."""
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