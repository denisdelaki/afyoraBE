# apps/core/urls.py

from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import (
    SignupView, LoginView, RefreshView, LogoutView, CompleteOnboardingView,
    VerifyOTPView, ResendOTPView, PasswordResetRequestView, PasswordResetConfirmView,
    UserViewSet, FacilityViewSet, DepartmentViewSet,
)

# ============================================================================
# ROUTER EXPLANATION
# ============================================================================
# 
# DefaultRouter automatically creates URL patterns from ViewSets.
# 
# For UserViewSet, it creates:
# POST   /users/              → create
# GET    /users/              → list
# GET    /users/{id}/         → retrieve
# PUT    /users/{id}/         → update
# DELETE /users/{id}/         → destroy
#
# Plus custom actions like:
# GET    /users/profile/      → custom action
# POST   /users/{id}/change-password/ → custom action

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'facilities', FacilityViewSet, basename='facility')
router.register(r'departments', DepartmentViewSet, basename='department')

# URL Patterns
urlpatterns = [
    # Authentication endpoints (no prefix)
    path('auth/signup/', SignupView.as_view(), name='signup'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', RefreshView.as_view(), name='refresh'),
    re_path(r'^auth/refresh$', RefreshView.as_view()),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    re_path(r'^auth/verify-otp$', VerifyOTPView.as_view()),
    path('auth/resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    re_path(r'^auth/resend-otp$', ResendOTPView.as_view()),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path(
        'auth/password-reset-confirm/<uid>/<token>/',
        PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    path('auth/onboarding/complete/', CompleteOnboardingView.as_view(), name='complete-onboarding'),
    
    # Resource endpoints (from router)
    path('', include(router.urls)),
]

# ============================================================================
# RESULTING API ENDPOINTS
# ============================================================================
# Authentication:
# POST   /api/auth/signup/           - Register new facility
# POST   /api/auth/login/            - Login user
# POST   /api/auth/logout/           - Logout user
#
# Users:
# GET    /api/users/                 - List users
# POST   /api/users/                 - Create user
# GET    /api/users/{id}/            - Get user details
# PUT    /api/users/{id}/            - Update user
# DELETE /api/users/{id}/            - Delete user
# GET    /api/users/profile/         - Get current user profile
# POST   /api/users/{id}/change-password/ - Change password
# GET    /api/users/staff/           - List staff members
#
# Facilities:
# GET    /api/facilities/            - List facilities
# GET    /api/facilities/{id}/       - Get facility details
#
# Departments:
# GET    /api/departments/           - List departments
# POST   /api/departments/           - Create department
# GET    /api/departments/{id}/      - Get department
# PUT    /api/departments/{id}/      - Update department
# DELETE /api/departments/{id}/      - Delete department
