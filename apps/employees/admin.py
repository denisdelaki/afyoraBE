from django.contrib import admin
from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
	list_display = (
		'employee_id',
		'name',
		'facility',
		'role',
		'department',
		'status',
		'shift',
		'join_date',
	)
	search_fields = ('employee_id', 'name', 'email', 'facility__name')
	list_filter = ('facility', 'status', 'shift', 'department')
