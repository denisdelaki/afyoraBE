# Afyora Backend - Quick Start Guide

## Overview

This guide walks you through building the complete Django backend for Afyora, the hospital management system. By the end, you'll have:

✅ User authentication (signup/login)  
✅ Multi-tenancy (multiple clinics/hospitals)  
✅ API endpoints for all features  
✅ Database models and migrations  
✅ Admin interface for management  
✅ Comprehensive understanding of Django

**Estimated time:** 4-6 hours for initial setup + learning

---

## What You'll Learn

1. **Django Fundamentals**
   - Models (database schema)
   - Views (request handling)
   - Serializers (data validation)
   - URLs (routing)
   - Admin interface

2. **Django REST Framework (DRF)**
   - Building APIs
   - Authentication (JWT)
   - Permissions
   - Pagination & Filtering

3. **Multi-Tenancy**
   - Data isolation per facility
   - Secure filtering
   - Role-based access control

4. **Best Practices**
   - Error handling
   - Logging & auditing
   - Code organization
   - Database design

---

## Prerequisites

✅ Python 3.8+ installed  
✅ PostgreSQL installed (or SQLite for development)  
✅ Git installed  
✅ Text editor/IDE (VS Code recommended)  
✅ Postman or similar for API testing

---

## PHASE 1: Project Setup (30 minutes)

### Step 1.1: Create Project Directory

```bash
mkdir afyora_backend
cd afyora_backend
```

### Step 1.2: Create Virtual Environment

```bash
# Create
python -m venv venv

# Activate
# On Mac/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 1.3: Install Dependencies

Copy the contents of `requirements_and_env.txt` into a `requirements.txt` file in your project root.

```bash
pip install -r requirements.txt
```

### Step 1.4: Create Django Project

```bash
# Create project
django-admin startproject afyora .

# Create apps
python manage.py startapp core
python manage.py startapp patients
python manage.py startapp appointments
python manage.py startapp billing
python manage.py startapp pharmacy
python manage.py startapp laboratory
python manage.py startapp radiology
python manage.py startapp inventory
python manage.py startapp employees
python manage.py startapp reports
```

Your structure should look like:

```
afyora_backend/
├── venv/
├── afyora/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/
│   ├── patients/
│   └── ... (other apps)
├── manage.py
├── requirements.txt
└── .env
```

### Step 1.5: Create .env File

Copy `.env.example` content and create `.env`:

```bash
touch .env
```

Edit `.env` and add:

```
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=afyora_db
DB_USER=postgres
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
EMAIL_HOST_USER=your-email@gmail.com
```

---

## PHASE 2: Configure Django (30 minutes)

### Step 2.1: Update settings.py

Replace `afyora/settings.py` with the content from `settings.py` provided.

**Key changes:**

- Add INSTALLED_APPS (all our apps + third-party)
- Configure CORS for Angular
- Set up JWT authentication
- Configure PostgreSQL database
- Set custom user model

### Step 2.2: Update URLs

**afyora/urls.py:**

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    # Add other app URLs as we create them
]
```

### Step 2.3: Test Django Setup

```bash
python manage.py check

# Output should be: "System check identified no issues (0 silenced)."
```

---

## PHASE 3: Create Core App (Authentication) (90 minutes)

This is the most important part. Read carefully!

### Step 3.1: Create Models

Copy content from `core_models.py` to `apps/core/models.py`

**What you're creating:**

- `Facility`: Clinic/Hospital (tenant)
- `User`: Custom user model with facility FK
- `Department`: Departments within facility
- `FacilityOnboarding`: Track setup progress
- `AuditLog`: Log all actions for compliance

### Step 3.2: Create Serializers

Copy content from `core_serializers.py` to `apps/core/serializers.py`

**What you're creating:**

- `SignupSerializer`: Validate signup form, create facility + user
- `LoginSerializer`: Authenticate user
- `UserSerializer`: Display user data
- `DepartmentSerializer`: Manage departments

**Key concept:** Serializers validate input AND serialize output to JSON

### Step 3.3: Create Views

Copy content from `core_views.py` to `apps/core/views.py`

**What you're creating:**

- `SignupView`: POST /api/auth/signup/
- `LoginView`: POST /api/auth/login/
- `UserViewSet`: CRUD for users
- `FacilityViewSet`: Read facility data
- `DepartmentViewSet`: CRUD for departments

**Key concept:** Views handle the actual request processing

### Step 3.4: Create URLs

Copy content from `core_urls.py` to `apps/core/urls.py`

### Step 3.5: Create Admin Interface

Copy content from `core_admin.py` to `apps/core/admin.py`

---

## PHASE 4: Database Setup (15 minutes)

### Step 4.1: Create Migrations

```bash
python manage.py makemigrations core
```

This creates the migration file based on your models.

### Step 4.2: Review Migrations (Optional)

```bash
python manage.py sqlmigrate core 0001
```

This shows the SQL that will be created.

### Step 4.3: Apply Migrations

```bash
python manage.py migrate
```

Creates database tables.

### Step 4.4: Create Superuser

```bash
python manage.py createsuperuser
```

This creates the admin account. Enter:

- Email: admin@example.com
- Password: SecurePass123!

---

## PHASE 5: Test the System (30 minutes)

### Step 5.1: Start Development Server

```bash
python manage.py runserver
```

Visit: http://localhost:8000/

### Step 5.2: Access Admin Panel

Visit: http://localhost:8000/admin/
Login with superuser credentials

### Step 5.3: Test Signup Endpoint

Using Postman or cURL:

```bash
curl -X POST http://localhost:8000/api/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{
    "facility_type": "hospital",
    "facility_name": "Test Hospital",
    "registration_number": "REG/2024/001",
    "admin_first_name": "John",
    "admin_last_name": "Doe",
    "email": "john@hospital.com",
    "phone": "+254712345678",
    "password": "TestPass123!",
    "password_confirm": "TestPass123!"
  }'
```

**Expected response:**

```json
{
  "organization_id": 1,
  "onboarding_required": true,
  "message": "Signup successful!"
}
```

### Step 5.4: Test Login Endpoint

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@hospital.com",
    "password": "TestPass123!"
  }'
```

**Expected response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "email": "john@hospital.com",
    "first_name": "John",
    "last_name": "Doe",
    "role": "facility_admin"
  }
}
```

### Step 5.5: Test Protected Endpoint

```bash
curl -X GET http://localhost:8000/api/users/profile/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Replace YOUR_ACCESS_TOKEN with the token from login response.

---

## PHASE 6: Create Other Apps (Ongoing)

Follow the pattern in `APP_CREATION_TEMPLATE.md` for each app:

1. **Patients**
   - Model: Patient with facility FK
   - Serializers: List, Detail, Create
   - Views: ViewSet with CRUD
   - Admin: Display in admin panel

2. **Appointments**
   - Model: Appointment with facility, patient, doctor FK
   - Similar structure as Patients

3. **Pharmacy**
   - Models: Drug, Prescription
   - Same pattern

**Key pattern for every app:**

```
Models (database schema)
    ↓
Serializers (validation + formatting)
    ↓
Views (API logic)
    ↓
URLs (routing)
    ↓
Admin (management interface)
    ↓
Migrations (apply to database)
```

---

## Important Concepts to Remember

### 1. Multi-Tenancy

**EVERY model must have:**

```python
facility = ForeignKey(Facility, on_delete=models.CASCADE)
```

**EVERY view must filter by:**

```python
def get_queryset(self):
    return MyModel.objects.filter(facility=self.request.user.facility)
```

❌ Wrong: `MyModel.objects.all()` (shows all data!)  
✅ Right: `MyModel.objects.filter(facility=...)`

### 2. Authentication Flow

1. Frontend sends email + password
2. Django verifies password
3. Django generates JWT token
4. Frontend stores token
5. Future requests include token in header
6. Django validates token, identifies user

### 3. Serializer Purpose

Serializers have TWO jobs:

**Input (Deserialization):**

```
JSON from API → Validate → Python objects
```

**Output (Serialization):**

```
Python objects → Validate fields → JSON
```

### 4. Soft Deletes

Never truly delete data:

```python
def perform_destroy(self, instance):
    instance.is_active = False
    instance.save()
```

This preserves audit trail and allows recovery.

---

## Common Issues & Solutions

### Issue 1: "ModuleNotFoundError: No module named 'rest_framework'"

**Solution:**

```bash
pip install -r requirements.txt
```

### Issue 2: Database connection error

**Solution:**

- Check PostgreSQL is running
- Check DB credentials in .env match PostgreSQL config
- For development, use SQLite: Change DB_ENGINE to 'django.db.backends.sqlite3'

### Issue 3: CORS errors in console

**Solution:**

- Check CORS_ALLOWED_ORIGINS in settings.py includes your frontend URL
- Restart Django server after changing settings

### Issue 4: "no such table: auth_user"

**Solution:**

```bash
python manage.py migrate
```

### Issue 5: Circular imports

**Solution:**
Import at function level, not module level:

```python
# ❌ Bad
from apps.patients.models import Patient

# ✅ Good
def my_function():
    from apps.patients.models import Patient
```

---

## Testing with Django Shell

```bash
python manage.py shell

# Test creating a facility
from core.models import Facility
facility = Facility.objects.create(
    name="Test Clinic",
    facility_type="clinic",
    registration_number="REG/001",
    email="clinic@test.com",
    phone="254712345678"
)
print(facility.name)  # "Test Clinic"

# Test creating a user
from core.models import User
user = User.objects.create_user(
    username="testdoc",
    email="doctor@clinic.com",
    password="TestPass123!",
    first_name="Test",
    last_name="Doctor",
    facility=facility,
    role="doctor"
)
print(user.get_full_name())  # "Test Doctor"

# Test login
user.check_password("TestPass123!")  # True
```

---

## Next: Frontend Integration

Once backend is ready, update Angular to use your API:

**In Angular environment:**

```typescript
export const environment = {
  production: false,
  apiUrl: "http://localhost:8000/api",
};
```

**In API service:**

```typescript
login(credentials: LoginRequest) {
  return this.http.post(
    `${this.apiUrl}/auth/login/`,
    credentials
  );
}
```

---

## Resources

- Django docs: https://docs.djangoproject.com
- DRF docs: https://www.django-rest-framework.org
- Real Python: https://realpython.com/django-rest-framework
- YouTube: "Django REST Framework Tutorial"

---

## File Checklist

Before moving forward, ensure you have:

- [ ] `afyora/settings.py` - Configured
- [ ] `afyora/urls.py` - Updated with API routes
- [ ] `apps/core/models.py` - All 5 models created
- [ ] `apps/core/serializers.py` - All serializers created
- [ ] `apps/core/views.py` - All views created
- [ ] `apps/core/urls.py` - URL routing
- [ ] `apps/core/admin.py` - Admin interface
- [ ] `.env` file - Environment variables
- [ ] Database migrations applied - `python manage.py migrate`
- [ ] Superuser created - `python manage.py createsuperuser`

---

## Congratulations! 🎉

You now have a fully functional Django backend for Afyora!

**Next steps:**

1. Build other apps (Patients, Appointments, etc.) using the template
2. Add permissions and role-based access control
3. Implement file uploads for documents/images
4. Add email notifications
5. Set up production server (Gunicorn + Nginx)
6. Deploy to AWS/DigitalOcean/Heroku

---

## Get Help

If you get stuck:

1. Check the COMPLETE_IMPLEMENTATION_GUIDE.md
2. Review error messages carefully (they usually tell you what's wrong)
3. Check Django logs: `logs/django.log`
4. Use `python manage.py shell` to test code
5. Use Django admin to inspect database

Good luck! 🚀
