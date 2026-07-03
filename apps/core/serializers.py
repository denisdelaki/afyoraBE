# apps/core/serializers.py

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from .models import User, Facility, Department, FacilityOnboarding
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
            'subscription_active', 'subscription_start_date',
            'subscription_end_date', 'onboarding_completed',
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
            'subscription_active', 'subscription_start_date',
            'subscription_end_date'
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'name': {
                'validators': []
            },
            'email': {
                'validators': []
            },
            'registration_number': {
                'validators': []
            },
        }


# ============================================================================
# USER SERIALIZERS
# ============================================================================

class UserSerializer(serializers.ModelSerializer):
    """
    Basic user serializer for list/detail views.
    Excludes password for security.
    """
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'facility', 'facility_name', 'phone',
            'department', 'is_active', 'is_verified', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Detailed user info including employment details.
    """
    facility_name = serializers.CharField(source='facility.name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone', 'date_of_birth', 'profile_picture',
            'facility', 'facility_name', 'employee_id', 'department',
            'license_number', 'specialization', 'is_active',
            'is_verified', 'last_login', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'last_login', 'created_at', 'updated_at']


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
        Should have uppercase, lowercase, number, special char.
        """
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
        
        # Common weak passwords
        weak_passwords = ['password', '123456', 'qwerty', 'admin']
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
    Handles user login authentication.
    """
    
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8
    )
    remember_me = serializers.BooleanField(
        required=False,
        default=False
    )
    
    def validate(self, data):
        """
        Authenticate user with email and password.
        """
        email = data.get('email')
        password = data.get('password')
        
        # Django authenticate() expects username, not email
        # Get user first
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid email or password."
            )
        
        # Check password
        if not user.check_password(password):
            raise serializers.ValidationError(
                "Invalid email or password."
            )
        
        # Check if account is active
        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been deactivated."
            )
        
        # Check if facility is still subscribed
        if user.facility and not user.facility.subscription_active:
            raise serializers.ValidationError(
                "Your facility's subscription has expired."
            )
        
        data['user'] = user
        return data


# ============================================================================
# DEPARTMENT SERIALIZER
# ============================================================================

class DepartmentSerializer(serializers.ModelSerializer):
    """
    Department management serializer.
    """
    head_name = serializers.CharField(
        source='head.get_full_name',
        read_only=True
    )
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'description', 'head', 'head_name',
            'email', 'phone', 'location', 'is_operational',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def validate(self, data):
        """Check department name is unique within facility"""
        facility = self.context['request'].user.facility
        
        if Department.objects.filter(
            facility=facility,
            name__iexact=data.get('name')
        ).exists():
            raise serializers.ValidationError(
                "A department with this name already exists."
            )
        
        return data


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