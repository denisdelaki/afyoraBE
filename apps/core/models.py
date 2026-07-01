# apps/core/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# ============================================================================
# ABSTRACT BASE MODEL
# ============================================================================
# This is a template that other models inherit from
# Reduces repetition (DRY - Don't Repeat Yourself)

class BaseModel(models.Model):
    """
    Abstract base model with common fields for all models.
    
    When a model inherits from this, it automatically gets:
    - created_at: timestamp when record was created
    - updated_at: timestamp when record was last modified
    - is_active: soft delete flag (mark as deleted without removing from DB)
    """
    created_at = models.DateTimeField(auto_now_add=True)
    # auto_now_add=True: Sets timestamp ONCE when created
    
    updated_at = models.DateTimeField(auto_now=True)
    # auto_now=True: Updates timestamp EVERY TIME record is saved
    
    is_active = models.BooleanField(default=True)
    # Allows "soft deletes" - mark as inactive instead of truly deleting
    
    class Meta:
        abstract = True
        # abstract=True means this model won't create a database table
        # It's only used for inheritance


# ============================================================================
# ORGANIZATION/FACILITY MODEL
# ============================================================================
# Represents a clinic or hospital using Afyora

class Facility(BaseModel):
    """
    Represents a clinic or hospital.
    
    Since Afyora supports multiple organizations, each clinic/hospital
    is stored here. All other data (patients, appointments, etc.) will
    reference this organization.
    
    Example:
    - Nairobi General Hospital (facility)
      └─ has many patients
      └─ has many appointments
      └─ has many users
    """
    
    FACILITY_TYPES = (
        ('hospital', 'Hospital'),
        ('clinic', 'Clinic'),
    )
    
    # Unique identifier - UUID would be better but using ID for now
    id = models.BigAutoField(primary_key=True)
    
    # From signup form
    name = models.CharField(max_length=255, unique=True)
    # Example: "Nairobi Hospital"
    
    facility_type = models.CharField(max_length=20, choices=FACILITY_TYPES)
    # Either 'hospital' or 'clinic'
    
    registration_number = models.CharField(max_length=100, unique=True)
    # Official registration/license number
    # Example: "REG/2024/001"
    
    # Contact Information
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Facility Details
    logo = models.ImageField(upload_to='facilities/logos/', null=True, blank=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    
    # Subscription/License Info
    subscription_active = models.BooleanField(default=True)
    # True if facility has paid subscription
    
    subscription_start_date = models.DateField(null=True, blank=True)
    subscription_end_date = models.DateField(null=True, blank=True)
    
    # Onboarding Status
    onboarding_completed = models.BooleanField(default=False)
    # After signup, facility needs to complete onboarding
    # (add departments, users, etc.)
    
    # Metrics
    total_patients = models.IntegerField(default=0)
    total_staff = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.name} ({self.facility_type})"
    
    class Meta:
        ordering = ['-created_at']
        # When fetching facilities, show newest first


# ============================================================================
# CUSTOM USER MODEL
# ============================================================================

class User(AbstractUser, BaseModel):
    """
    Custom user model for the system.
    
    AbstractUser extends Django's built-in User (has username, password, etc.)
    and adds our custom fields.
    
    Each user belongs to ONE facility (organization).
    This is the multi-tenancy key - filters data by facility.
    """
    
    ROLE_CHOICES = (
        ('admin', 'Administrator'),           # System admin
        ('facility_admin', 'Facility Admin'),  # Clinic/hospital owner
        ('doctor', 'Doctor'),
        ('nurse', 'Nurse'),
        ('receptionist', 'Receptionist'),
        ('pharmacist', 'Pharmacist'),
        ('lab_technician', 'Lab Technician'),
        ('radiologist', 'Radiologist'),
        ('accountant', 'Accountant'),
        ('manager', 'Manager'),
        ('staff', 'General Staff'),
    )
    
    # Link user to a facility
    # This is CRITICAL for multi-tenancy
    # ForeignKey = "many users belong to one facility"
    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        # on_delete=models.PROTECT: Can't delete facility while users exist
        related_name='users',
        # Allows: facility.users.all() to get all users in facility
        null=True,
        blank=True
        # null=True allows for super admins not tied to a facility
    )
    
    # User details
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='users/profiles/', null=True, blank=True)
    
    # Employment info (if staff member)
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    # Example: "Cardiology", "Reception"
    
    license_number = models.CharField(max_length=100, blank=True)
    # For doctors, nurses - professional license
    
    specialization = models.CharField(max_length=200, blank=True)
    # For doctors - what they specialize in
    
    # Account status
    is_verified = models.BooleanField(default=False)
    # Email verified?
    
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_device = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"
    
    class Meta:
        ordering = ['-created_at']
        # Newest users first


# ============================================================================
# FACILITY ONBOARDING MODEL
# ============================================================================
# Tracks what the facility has completed during setup

class FacilityOnboarding(BaseModel):
    """
    Tracks onboarding progress for a facility.
    
    After signup, facilities must:
    1. Add basic info (departments, etc.)
    2. Add staff members
    3. Configure system settings
    
    This model tracks which steps are done.
    """
    
    facility = models.OneToOneField(
        Facility,
        on_delete=models.CASCADE,
        # CASCADE: If facility is deleted, this is too
        related_name='onboarding'
    )
    
    # Onboarding steps
    basic_info_completed = models.BooleanField(default=False)
    staff_added = models.BooleanField(default=False)
    departments_configured = models.BooleanField(default=False)
    settings_configured = models.BooleanField(default=False)
    
    # Overall status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def check_completion(self):
        """
        Automatically check if all steps are done.
        Call this after each step is completed.
        """
        if all([
            self.basic_info_completed,
            self.staff_added,
            self.departments_configured,
            self.settings_configured
        ]):
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()
    
    def __str__(self):
        return f"Onboarding - {self.facility.name}"


# ============================================================================
# FACILITY DEPARTMENT MODEL
# ============================================================================
# Different departments within a facility

class Department(BaseModel):
    """
    Departments within a facility.
    
    Example departments:
    - Cardiology
    - Orthopedics
    - Emergency
    - Pediatrics
    """
    
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='departments'
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_departments'
        # A doctor can head multiple departments
    )
    
    # Contact
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=100, blank=True)
    # Building/Floor info
    
    # Settings
    is_operational = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ('facility', 'name')
        # Can't have two departments with same name in same facility
    
    def __str__(self):
        return f"{self.name} - {self.facility.name}"


# ============================================================================
# AUDIT LOG MODEL
# ============================================================================
# Track who did what for security and compliance

class AuditLog(BaseModel):
    """
    Logs all important actions for compliance and security.
    
    Useful for:
    - Who accessed what data
    - What was created/modified/deleted
    - Detecting suspicious activity
    - HIPAA compliance (healthcare regulations)
    """
    
    ACTION_CHOICES = (
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('export', 'Export'),
        ('login', 'Login'),
    )
    
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    # What action was performed
    
    model_name = models.CharField(max_length=100)
    # Which model was affected (Patient, Appointment, etc.)
    
    object_id = models.CharField(max_length=100)
    # Which specific record (patient #123, appointment #456)
    
    description = models.TextField()
    # Details about the action
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['facility', 'created_at']),
            models.Index(fields=['user', 'action']),
        ]
        # Indexes speed up queries
    
    def __str__(self):
        return f"{self.user} - {self.action} - {self.model_name}"