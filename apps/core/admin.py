# apps/core/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, Facility, Department, FacilityOnboarding, AuditLog


# ============================================================================
# ADMIN INTERFACE EXPLANATION
# ============================================================================
# 
# Django Admin allows staff to:
# - View/edit data in database
# - Filter and search records
# - Perform bulk actions
# - Access via: http://localhost:8000/admin
#
# Register models so they appear in admin panel.


# ============================================================================
# FACILITY ADMIN
# ============================================================================

@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    """
    Admin interface for managing facilities (clinics/hospitals).
    """
    
    # Columns displayed in list view
    list_display = (
        'name',
        'facility_type_badge',
        'registration_number',
        'subscription_status',
        'total_patients',
        'created_at'
    )
    
    # Columns that are clickable links to detail page
    list_display_links = ('name',)
    
    # Add filters on the right side
    list_filter = ('facility_type', 'subscription_active', 'created_at')
    
    # Add search box
    search_fields = ('name', 'registration_number', 'email')
    
    # Read-only fields (can view but not edit)
    readonly_fields = ('id', 'created_at', 'updated_at', 'users_count')
    
    # Organize fields into sections (fieldsets)
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'facility_type', 'registration_number')
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'address', 'city', 'country')
        }),
        ('Details', {
            'fields': ('logo', 'description', 'website')
        }),
        ('Subscription', {
            'fields': (
                'subscription_active',
                'subscription_start_date',
                'subscription_end_date'
            )
        }),
        ('Status', {
            'fields': ('onboarding_completed', 'total_patients', 'total_staff')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'is_active'),
            'classes': ('collapse',)  # Hide by default
        }),
    )
    
    # Custom actions
    actions = ['activate_subscription', 'deactivate_subscription']
    
    def facility_type_badge(self, obj):
        """Display facility type with color badge"""
        colors = {
            'hospital': '#2ecc71',  # Green
            'clinic': '#3498db'     # Blue
        }
        color = colors.get(obj.facility_type, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_facility_type_display()
        )
    facility_type_badge.short_description = 'Type'
    
    def subscription_status(self, obj):
        """Display subscription status with color"""
        if obj.subscription_active:
            badge = '<span style="background-color: #27ae60; color: white; padding: 3px 10px; border-radius: 3px;">Active</span>'
        else:
            badge = '<span style="background-color: #e74c3c; color: white; padding: 3px 10px; border-radius: 3px;">Inactive</span>'
        return format_html(badge)
    subscription_status.short_description = 'Subscription'
    
    def users_count(self, obj):
        """Show number of users"""
        return obj.users.count()
    users_count.short_description = 'Total Users'
    
    def activate_subscription(self, request, queryset):
        """Bulk action: activate subscription"""
        updated = queryset.update(subscription_active=True)
        self.message_user(request, f'{updated} facilities activated.')
    activate_subscription.short_description = 'Activate subscription'
    
    def deactivate_subscription(self, request, queryset):
        """Bulk action: deactivate subscription"""
        updated = queryset.update(subscription_active=False)
        self.message_user(request, f'{updated} facilities deactivated.')
    deactivate_subscription.short_description = 'Deactivate subscription'


# ============================================================================
# CUSTOM USER ADMIN
# ============================================================================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin interface for managing users.
    Extends Django's default UserAdmin.
    """
    
    # Additional display fields
    list_display = (
        'email',
        'get_full_name',
        'role_badge',
        'facility_name',
        'is_active',
        'is_verified',
        'created_at'
    )
    
    list_display_links = ('email',)
    
    # Filters
    list_filter = (
        'role', 'facility', 'is_active', 'is_verified',
        'created_at', 'last_login'
    )
    
    # Search
    search_fields = ('email', 'first_name', 'last_name', 'username')
    
    # Read-only
    readonly_fields = (
        'username', 'created_at', 'updated_at', 'last_login',
        'last_login_ip', 'last_login_device'
    )
    
    # Field organization
    fieldsets = (
        ('Authentication', {
            'fields': ('username', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'date_of_birth')
        }),
        ('Role & Facility', {
            'fields': ('role', 'facility')
        }),
        ('Employment', {
            'fields': (
                'employee_id', 'department', 'license_number', 'specialization'
            ),
            'classes': ('collapse',)
        }),
        ('Account Status', {
            'fields': ('is_active', 'is_verified')
        }),
        ('Login History', {
            'fields': (
                'last_login', 'last_login_ip', 'last_login_device'
            ),
            'classes': ('collapse',)
        }),
        ('Profile', {
            'fields': ('profile_picture',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # Actions
    actions = ['activate_users', 'deactivate_users', 'verify_users']
    
    def role_badge(self, obj):
        """Display role with color"""
        colors = {
            'admin': '#e74c3c',           # Red
            'facility_admin': '#e67e22',  # Orange
            'doctor': '#3498db',          # Blue
            'nurse': '#9b59b6',           # Purple
            'pharmacist': '#1abc9c',      # Teal
        }
        color = colors.get(obj.role, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_role_display()
        )
    role_badge.short_description = 'Role'
    
    def facility_name(self, obj):
        """Display facility name"""
        return obj.facility.name if obj.facility else 'N/A'
    facility_name.short_description = 'Facility'
    
    def activate_users(self, request, queryset):
        """Bulk action: activate users"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} users activated.')
    activate_users.short_description = 'Activate selected users'
    
    def deactivate_users(self, request, queryset):
        """Bulk action: deactivate users"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} users deactivated.')
    deactivate_users.short_description = 'Deactivate selected users'
    
    def verify_users(self, request, queryset):
        """Bulk action: verify users"""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} users verified.')
    verify_users.short_description = 'Verify selected users'


# ============================================================================
# DEPARTMENT ADMIN
# ============================================================================

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin interface for departments."""
    
    list_display = ('name', 'facility_name', 'head_name', 'is_operational')
    list_display_links = ('name',)
    list_filter = ('facility', 'is_operational')
    search_fields = ('name', 'facility__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('facility', 'name', 'description')
        }),
        ('Management', {
            'fields': ('head',)
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'location')
        }),
        ('Status', {
            'fields': ('is_operational',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def facility_name(self, obj):
        return obj.facility.name
    facility_name.short_description = 'Facility'
    
    def head_name(self, obj):
        return obj.head.get_full_name() if obj.head else 'Unassigned'
    head_name.short_description = 'Department Head'


# ============================================================================
# FACILITY ONBOARDING ADMIN
# ============================================================================

@admin.register(FacilityOnboarding)
class FacilityOnboardingAdmin(admin.ModelAdmin):
    """Admin interface for onboarding progress."""
    
    list_display = (
        'facility_name',
        'basic_info',
        'staff_added',
        'departments',
        'settings',
        'is_completed'
    )
    list_display_links = ('facility_name',)
    list_filter = ('is_completed', 'created_at')
    search_fields = ('facility__name',)
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    
    fieldsets = (
        ('Facility', {
            'fields': ('facility',)
        }),
        ('Completion Steps', {
            'fields': (
                'basic_info_completed',
                'staff_added',
                'departments_configured',
                'settings_configured'
            )
        }),
        ('Status', {
            'fields': ('is_completed', 'completed_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def facility_name(self, obj):
        return obj.facility.name
    facility_name.short_description = 'Facility'
    
    def basic_info(self, obj):
        return '✓' if obj.basic_info_completed else '✗'
    basic_info.short_description = 'Basic Info'
    
    def staff_added(self, obj):
        return '✓' if obj.staff_added else '✗'
    staff_added.short_description = 'Staff Added'
    
    def departments(self, obj):
        return '✓' if obj.departments_configured else '✗'
    departments.short_description = 'Departments'
    
    def settings(self, obj):
        return '✓' if obj.settings_configured else '✗'
    settings.short_description = 'Settings'


# ============================================================================
# AUDIT LOG ADMIN
# ============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for audit logs (read-only)."""
    
    list_display = (
        'created_at',
        'user_name',
        'action_badge',
        'model_name',
        'facility_name'
    )
    list_display_links = None  # No clickable links (read-only)
    list_filter = ('action', 'model_name', 'facility', 'created_at')
    search_fields = ('user__email', 'description', 'facility__name')
    readonly_fields = (
        'facility', 'user', 'action', 'model_name', 'object_id',
        'description', 'ip_address', 'user_agent', 'created_at'
    )
    
    # Prevent editing and deletion
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Keep audit logs read-only for most users, but allow users who
        # explicitly have delete permission (including superusers) so
        # cascading deletes from related models can proceed in admin.
        return request.user.is_superuser or request.user.has_perm('core.delete_auditlog')
    
    fieldsets = (
        ('Action Details', {
            'fields': ('action', 'user', 'facility')
        }),
        ('Target', {
            'fields': ('model_name', 'object_id')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Request Info', {
            'fields': ('ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )
    
    def user_name(self, obj):
        return obj.user.get_full_name() if obj.user else 'System'
    user_name.short_description = 'User'
    
    def action_badge(self, obj):
        colors = {
            'create': '#27ae60',
            'update': '#3498db',
            'delete': '#e74c3c',
            'view': '#95a5a6',
            'export': '#f39c12',
            'login': '#9b59b6',
        }
        color = colors.get(obj.action, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_badge.short_description = 'Action'
    
    def facility_name(self, obj):
        return obj.facility.name if obj.facility else 'N/A'
    facility_name.short_description = 'Facility'