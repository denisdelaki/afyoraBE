# apps/core/serializers.py

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from .models import User, Facility, Department, FacilityOnboarding, FacilityRole, FacilitySubscriptionPayment, ALL_MODULE_PERMISSIONS
import re


# ============================================================================
# SERIALIZERS EXPLANATION
# ============================================================================
# Serializers convert Python objects ↔ JSON and handle validation
#
# Example:
# Frontend sends JSON:
#   {
#     "email": "doctor@clinic.com",
#     "password": "secure123"
#   }
#
# Serializer converts it to Python:
#   {"email": "doctor@clinic.com", "password": "secure123"}
#
# Validates it (is email valid? is password strong?)
# Creates User object in database
# Returns JSON response to frontend


# ============================================================================
# FACILITY ROLE SERIALIZERS (Dynamic RBAC)
# ============================================================================

class FacilityRoleSerializer(serializers.ModelSerializer):
    """
    Serializer for creating, reading, updating, and deleting custom facility roles.
    Each role carries a JSON permissions map keyed by module slug.
    """
    user_count = serializers.SerializerMethodField()
    employee_count = serializers.SerializerMethodField()

    class Meta:
        model = FacilityRole
        fields = [
            'id', 'name', 'description', 'permissions',
            'is_system_role', 'user_count', 'employee_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_system_role', 'created_at', 'updated_at']

    def get_user_count(self, obj):
        return obj.users.count()

    def get_employee_count(self, obj):
        return obj.employees.count()

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Role name must be at least 2 characters.')
        return value

    def validate_permissions(self, value):
        """Ensure permissions dict only contains valid module keys."""
        if not isinstance(value, dict):
            raise serializers.ValidationError('Permissions must be a JSON object.')
        invalid_keys = set(value.keys()) - set(ALL_MODULE_PERMISSIONS)
        if invalid_keys:
            raise serializers.ValidationError(
                f'Invalid permission keys: {sorted(invalid_keys)}. '
                f'Valid keys are: {ALL_MODULE_PERMISSIONS}'
            )
        # Ensure all values are booleans
        for key, val in value.items():
            if not isinstance(val, bool):
                raise serializers.ValidationError(
                    f'Permission value for "{key}" must be true or false.'
                )
        return value

    def validate(self, data):
        """Check role name is unique within facility."""
        request = self.context.get('request')
        facility = getattr(getattr(request, 'user', None), 'facility', None)
        instance = getattr(self, 'instance', None)
        role_name = data.get('name')

        if role_name and facility and FacilityRole.objects.filter(
            facility=facility,
            name__iexact=role_name,
        ).exclude(pk=getattr(instance, 'pk', None)).exists():
            raise serializers.ValidationError(
                {'name': 'A role with this name already exists in your facility.'}
            )
        return data


# ============================================================================
# FACILITY SERIALIZERS
# ============================================================================

class FacilityListSerializer(serializers.ModelSerializer):
    """
    Simple facility info for list views.
    Excludes sensitive data.
    """
    class Meta:
        model = Facility
        fields = [
            'id', 'name', 'facility_type', 'email', 'phone',
            'city', 'subscription_active', 'total_patients',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class FacilityDetailSerializer(serializers.ModelSerializer):
    """
    Complete facility info including related data.
    Used when viewing single facility.
    """
    departments_count = serializers.SerializerMethodField()
    users_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Facility
        fields = [
            'id', 'name', 'facility_type', 'registration_number',
            'email', 'phone', 'address', 'city', 'country',
            'logo', 'description', 'website',
            'subscription_active', 'subscription_package', 'subscription_billing_cycle',
            'subscription_start_date', 'subscription_end_date', 'onboarding_completed',
            'total_patients', 'total_staff',
            'departments_count', 'users_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_departments_count(self, obj):
        """Get number of departments in this facility"""
        return obj.departments.count()
    
    def get_users_count(self, obj):
        """Get number of users in this facility"""
        return obj.users.count()


class FacilityWriteSerializer(serializers.ModelSerializer):
    """
    Writable serializer for creating facilities directly via the API.
    """

    def validate_name(self, value):
        if Facility.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError(
                'A facility with this name already exists.'
            )
        return value

    def validate_email(self, value):
        if Facility.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'A facility with this email already exists.'
            )
        return value

    def validate_registration_number(self, value):
        if Facility.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError(
                'A facility with this registration number already exists.'
            )
        return value

    class Meta:
        model = Facility
        fields = [
            'id', 'name', 'facility_type', 'registration_number',
            'email', 'phone', 'address', 'city', 'country',
            'logo', 'description', 'website',
            'subscription_active', 'subscription_package', 'subscription_billing_cycle',
            'subscription_start_date', 'subscription_end_date'
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'name': {'validators': []},
            'email': {'validators': []},
            'registration_number': {'validators': []},
        }


class FacilityUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for Facility Admins updating their facility details.
    """
    class Meta:
        model = Facility
        fields = [
            'id', 'name', 'facility_type', 'registration_number',
            'email', 'phone', 'address', 'city', 'country',
            'logo', 'description', 'website'
        ]
        read_only_fields = ['id', 'registration_number']

    def validate_name(self, value):
        instance = getattr(self, 'instance', None)
        if Facility.objects.filter(name__iexact=value).exclude(pk=instance.pk if instance else None).exists():
            raise serializers.ValidationError('A facility with this name already exists.')
        return value

    def validate_email(self, value):
        instance = getattr(self, 'instance', None)
        if Facility.objects.filter(email__iexact=value).exclude(pk=instance.pk if instance else None).exists():
            raise serializers.ValidationError('A facility with this email already exists.')
        return value


class FacilitySubscriptionPaymentSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True)

    class Meta:
        model = FacilitySubscriptionPayment
        fields = [
            'id', 'facility', 'facility_name', 'package', 'billing_cycle',
            'amount', 'payment_method', 'phone_number',
            'transaction_reference', 'status', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'facility', 'created_at']


class SubscribePackageSerializer(serializers.Serializer):
    package = serializers.ChoiceField(choices=Facility.PACKAGE_CHOICES)
    billing_cycle = serializers.ChoiceField(choices=Facility.CYCLE_CHOICES, default='monthly')
    payment_method = serializers.ChoiceField(choices=FacilitySubscriptionPayment.METHOD_CHOICES, default='mpesa')
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    card_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    card_expiry = serializers.CharField(max_length=10, required=False, allow_blank=True)
    card_cvv = serializers.CharField(max_length=10, required=False, allow_blank=True)


# ============================================================================
# USER SERIALIZERS
# ============================================================================

class UserSerializer(serializers.ModelSerializer):
    """
    Basic user serializer for list/detail views.
    Excludes password for security.
    Includes custom_role details and permissions for frontend RBAC.
    """
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    custom_role_id = serializers.PrimaryKeyRelatedField(
        source='custom_role', read_only=True
    )
    custom_role_name = serializers.CharField(
        source='custom_role.name', read_only=True, default=None
    )
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'facility', 'facility_name', 'phone',
            'department', 'is_active', 'is_verified', 'must_change_password',
            'custom_role_id', 'custom_role_name', 'permissions',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_permissions(self, obj):
        """
        Return the effective permissions for this user.
        - facility_admin / admin: all modules = True
        - custom_role present: use its permissions map
        - fallback: use static role defaults
        """
        static_role = getattr(obj, 'role', 'staff')

        if static_role in ('admin', 'facility_admin'):
            return {key: True for key in ALL_MODULE_PERMISSIONS}

        if obj.custom_role_id:
            perms = getattr(obj.custom_role, 'permissions', {}) or {}
            # Fill any missing keys with False
            return {key: bool(perms.get(key, False)) for key in ALL_MODULE_PERMISSIONS}

        # Static fallback defaults
        STATIC_DEFAULTS = {
            'doctor':        {'patients', 'appointments', 'laboratory', 'ehr', 'visit_queue'},
            'nurse':         {'patients', 'appointments', 'ehr', 'visit_queue'},
            'receptionist':  {'patients', 'appointments', 'visit_queue'},
            'pharmacist':    {'pharmacy', 'inventory'},
            'lab_technician':{'laboratory', 'patients'},
            'radiologist':   {'radiology', 'patients'},
            'accountant':    {'billing', 'reports'},
            'hr':            {'employees', 'departments'},
            'manager':       set(ALL_MODULE_PERMISSIONS) - {'roles'},
            'staff':         set(),
        }
        allowed = STATIC_DEFAULTS.get(static_role, set())
        return {key: (key in allowed) for key in ALL_MODULE_PERMISSIONS}


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Detailed user info including employment details and effective permissions.
    """
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    custom_role_id = serializers.PrimaryKeyRelatedField(
        source='custom_role', read_only=True
    )
    custom_role_name = serializers.CharField(
        source='custom_role.name', read_only=True, default=None
    )
    custom_role_permissions = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'date_of_birth', 'profile_picture',
            'facility', 'facility_name', 'employee_id', 'department',
            'license_number', 'specialization', 'is_active',
            'is_verified', 'must_change_password', 'last_login',
            'custom_role_id', 'custom_role_name', 'custom_role_permissions',
            'permissions',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_login', 'created_at', 'updated_at']

    def get_custom_role_permissions(self, obj):
        if obj.custom_role:
            return obj.custom_role.permissions
        return None

    def get_permissions(self, obj):
        """Mirror of UserSerializer.get_permissions for consistency."""
        static_role = getattr(obj, 'role', 'staff')
        if static_role in ('admin', 'facility_admin'):
            return {key: True for key in ALL_MODULE_PERMISSIONS}
        if obj.custom_role_id:
            perms = getattr(obj.custom_role, 'permissions', {}) or {}
            return {key: bool(perms.get(key, False)) for key in ALL_MODULE_PERMISSIONS}
        STATIC_DEFAULTS = {
            'doctor':        {'patients', 'appointments', 'laboratory', 'ehr', 'visit_queue'},
            'nurse':         {'patients', 'appointments', 'ehr', 'visit_queue'},
            'receptionist':  {'patients', 'appointments', 'visit_queue'},
            'pharmacist':    {'pharmacy', 'inventory'},
            'lab_technician':{'laboratory', 'patients'},
            'radiologist':   {'radiology', 'patients'},
            'accountant':    {'billing', 'reports'},
            'hr':            {'employees', 'departments'},
            'manager':       set(ALL_MODULE_PERMISSIONS) - {'roles'},
            'staff':         set(),
        }
        allowed = STATIC_DEFAULTS.get(static_role, set())
        return {key: (key in allowed) for key in ALL_MODULE_PERMISSIONS}


# ============================================================================
# SIGNUP SERIALIZER - THE MOST IMPORTANT ONE
# ============================================================================

class SignupSerializer(serializers.Serializer):
    """
    Handles facility signup (new clinic/hospital registration).
    
    This is more complex because it creates TWO things:
    1. A Facility (the clinic/hospital)
    2. An admin User (the clinic owner)
    
    Flow:
    Frontend sends signup form →
    Serializer validates all data →
    Creates Facility in database →
    Creates admin User in database →
    Returns organizationId & onboarding status
    """
    
    # Facility Information
    facility_type = serializers.ChoiceField(
        choices=['hospital', 'clinic'],
        required=True,
        error_messages={
            'invalid_choice': 'Facility type must be "hospital" or "clinic"'
        }
    )
    
    facility_name = serializers.CharField(
        max_length=255,
        required=True,
        error_messages={
            'blank': 'Facility name is required',
            'max_length': 'Facility name cannot exceed 255 characters'
        }
    )
    
    registration_number = serializers.CharField(
        max_length=100,
        required=True,
        help_text='Official registration/license number'
    )
    
    # Admin User Information
    admin_first_name = serializers.CharField(
        max_length=150,
        required=True,
        error_messages={'blank': 'Admin first name is required'}
    )
    
    admin_last_name = serializers.CharField(
        max_length=150,
        required=True,
        error_messages={'blank': 'Admin last name is required'}
    )
    
    email = serializers.EmailField(
        required=True,
        error_messages={
            'invalid': 'Enter a valid email address',
            'blank': 'Email is required'
        }
    )
    
    phone = serializers.CharField(
        max_length=20,
        required=True
    )
    
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        # write_only=True: Password is never returned in responses
        required=True,
        help_text='Password must be at least 8 characters'
    )
    
    password_confirm = serializers.CharField(
        min_length=8,
        write_only=True,
        required=True,
        help_text='Confirm password'
    )
    
    # ========================================================================
    # VALIDATION METHODS
    # ========================================================================
    
    def validate_facility_name(self, value):
        """
        Custom validation for facility name.
        Check if name is already taken.
        """
        if Facility.objects.filter(name__iexact=value).exists():
            # iexact = case-insensitive search
            raise serializers.ValidationError(
                "A facility with this name already exists."
            )
        
        if len(value.strip()) < 3:
            raise serializers.ValidationError(
                "Facility name must be at least 3 characters."
            )
        
        return value
    
    def validate_registration_number(self, value):
        """Check if registration number is unique"""
        if Facility.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError(
                "A facility with this registration number already exists."
            )
        return value
    
    def validate_email(self, value):
        """Check if email is already registered"""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists. Try logging in."
            )
        return value
    
    def validate_password(self, value):
        """
        Validate password strength.
        Must be at least 10 characters, have uppercase, lowercase, number, special char.
        """
        if len(value) < 10:
            raise serializers.ValidationError(
                "Password must be at least 10 characters long."
            )

        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )
        
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )
        
        if not re.search(r'[0-9]', value):
            raise serializers.ValidationError(
                "Password must contain at least one number."
            )

        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|~`]', value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )
        
        # Common weak passwords
        weak_passwords = ['password', '123456', 'qwerty', 'admin', 'password123!']
        if value.lower() in weak_passwords:
            raise serializers.ValidationError(
                "This password is too common. Please choose a stronger one."
            )
        
        return value
    
    def validate(self, data):
        """
        Validate the entire serializer.
        Called after individual field validations.
        """
        # Check passwords match
        if data.get('password') != data.get('password_confirm'):
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match.'
            })
        
        # Remove password_confirm (we don't need it anymore)
        data.pop('password_confirm')
        
        return data
    
    # ========================================================================
    # CREATE METHOD - ACTUALLY SAVES TO DATABASE
    # ========================================================================
    
    def create(self, validated_data):
        """
        After validation passes, create the facility and user.
        This is called when serializer.save() is invoked.
        """
        
        # Extract data
        facility_type = validated_data.pop('facility_type')
        facility_name = validated_data.pop('facility_name')
        registration_number = validated_data.pop('registration_number')
        admin_first_name = validated_data.pop('admin_first_name')
        admin_last_name = validated_data.pop('admin_last_name')
        email = validated_data.pop('email')
        phone = validated_data.pop('phone')
        password = validated_data.pop('password')
        
        # STEP 1: Create the Facility
        facility = Facility.objects.create(
            name=facility_name,
            facility_type=facility_type,
            registration_number=registration_number,
            email=email,
            phone=phone,
            subscription_active=True
            # By default, new facilities are active
        )
        
        # STEP 2: Create the Admin User
        # Generate username from email (first part before @)
        username = email.split('@')[0]
        
        # Ensure username is unique
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        admin_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            phone=phone,
            facility=facility,
            role='facility_admin'
            # This user is the facility admin
        )
        
        # STEP 3: Create Onboarding Record
        FacilityOnboarding.objects.create(
            facility=facility,
            basic_info_completed=True
            # Signup completes basic info step
        )
        
        # Return facility (to access in view)
        return facility


# ============================================================================
# LOGIN SERIALIZER
# ============================================================================

class LoginSerializer(serializers.Serializer):
    """
    Handles user login authentication and optional first-time password update.
    """
    
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=1
    )
    remember_me = serializers.BooleanField(
        required=False,
        default=False
    )
    old_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    new_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    confirm_password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    
    def to_internal_value(self, data):
        payload = dict(data)
        if not payload.get('old_password') and payload.get('oldPassword'):
            payload['old_password'] = payload.get('oldPassword')
        if not payload.get('new_password') and payload.get('newPassword'):
            payload['new_password'] = payload.get('newPassword')
        if not payload.get('confirm_password') and payload.get('confirmPassword'):
            payload['confirm_password'] = payload.get('confirmPassword')
        return super().to_internal_value(payload)

    def validate(self, data):
        """
        Authenticate user with email and password.
        """
        email = data.get('email')
        password = data.get('password')
        old_password = data.get('old_password') or password
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid email or password."
            )
        
        if not user.check_password(password) and not user.check_password(old_password):
            raise serializers.ValidationError(
                "Invalid email or password."
            )
        
        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been deactivated."
            )
        
        if user.facility and not user.facility.subscription_active:
            raise serializers.ValidationError(
                "Your facility's subscription has expired."
            )

        if getattr(user, 'must_change_password', False):
            if not new_password:
                data['require_password_change'] = True
                data['user'] = user
                return data

            if new_password != confirm_password:
                raise serializers.ValidationError(
                    {"confirm_password": "New password and confirm password do not match."}
                )

            if len(new_password) < 8:
                raise serializers.ValidationError(
                    {"new_password": "New password must be at least 8 characters long."}
                )

            if new_password == password or new_password == old_password:
                raise serializers.ValidationError(
                    {"new_password": "New password must be different from your temporary password."}
                )

            data['perform_password_change'] = True
        
        data['user'] = user
        return data


# ============================================================================
# DEPARTMENT SERIALIZER
# ============================================================================

class DepartmentSerializer(serializers.ModelSerializer):
    """
    Department management serializer.
    """
    head = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    head_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'head', 'head_name',
            'email', 'phone', 'location', 'is_operational',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.head is not None:
            data['head'] = str(instance.head.pk)
            data['head_name'] = instance.head.get_full_name() or instance.head.username
        else:
            data['head'] = instance.head_name
            data['head_name'] = instance.head_name

        return data

    def validate_head(self, value):
        if value is None:
            return ''

        return value.strip()
    
    def validate(self, data):
        """Check department name is unique within facility"""
        facility = self.context['request'].user.facility
        instance = getattr(self, 'instance', None)
        department_name = data.get('name')
        
        if department_name and Department.objects.filter(
            facility=facility,
            name__iexact=department_name
        ).exclude(pk=getattr(instance, 'pk', None)).exists():
            raise serializers.ValidationError(
                "A department with this name already exists."
            )

        return data

    def create(self, validated_data):
        head_value = validated_data.pop('head', '')

        if isinstance(head_value, User):
            validated_data['head'] = head_value
            validated_data['head_name'] = head_value.get_full_name() or head_value.username
        else:
            validated_data['head'] = None
            validated_data['head_name'] = head_value

        return super().create(validated_data)

    def update(self, instance, validated_data):
        head_value = validated_data.pop('head', instance.head_name)

        if isinstance(head_value, User):
            validated_data['head'] = head_value
            validated_data['head_name'] = head_value.get_full_name() or head_value.username
        else:
            validated_data['head'] = None
            validated_data['head_name'] = head_value

        return super().update(instance, validated_data)


# ============================================================================
# RESPONSE SERIALIZERS - Data returned to frontend
# ============================================================================

class LoginResponseSerializer(serializers.Serializer):
    """
    Structured response for login.
    Matches the LoginResponse type from Angular.
    """
    access_token = serializers.CharField()
    refresh_token = serializers.CharField(required=False, allow_blank=True)
    user = UserSerializer()


class SignupResponseSerializer(serializers.Serializer):
    """
    Structured response for signup.
    Matches the SignupResponse type from Angular.
    """
    organization_id = serializers.IntegerField()
    onboarding_required = serializers.BooleanField()
    message = serializers.CharField()


# ============================================================================
# OTP SERIALIZERS
# ============================================================================

class VerifyOTPSerializer(serializers.Serializer):
    """
    Serializer for verifying 6-digit email OTP.
    Supports 'otp' or 'code' field and 'email'.
    """
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=False, max_length=6, min_length=6)
    code = serializers.CharField(required=False, max_length=6, min_length=6)

    def to_internal_value(self, data):
        payload = dict(data)
        if not payload.get('otp') and payload.get('code'):
            payload['otp'] = payload.get('code')
        return super().to_internal_value(payload)

    def validate(self, data):
        if not data.get('otp'):
            raise serializers.ValidationError({'otp': 'OTP code is required.'})
        return data


class ResendOTPSerializer(serializers.Serializer):
    """
    Serializer for triggering resend OTP to an email.
    """
    email = serializers.EmailField(required=True)


# ============================================================================
# PASSWORD RESET SERIALIZERS
# ============================================================================

class PasswordResetRequestSerializer(serializers.Serializer):
    """Validate the email supplied when requesting a password-reset link."""

    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validate a new password supplied with a password-reset token."""

    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        if len(value) < 10:
            raise serializers.ValidationError("Password must be at least 10 characters long.")
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[0-9]', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|~`]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': 'Passwords do not match.'}
            )

        user = self.context.get('user')
        validate_password(data['new_password'], user=user)
        return data
