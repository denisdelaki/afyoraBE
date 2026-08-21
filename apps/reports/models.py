from django.db import models
from core.models import Facility


class SavedReport(models.Model):
    CHART_TYPE_CHOICES = [
        ('line', 'Line Chart'),
        ('bar', 'Bar Chart'),
    ]

    REPORT_TYPE_CHOICES = [
        ('general', 'General Overview'),
        ('patients', 'Patient Growth Report'),
        ('pharmacy', 'Pharmacy Performance'),
        ('inventory', 'Inventory Status'),
        ('laboratory', 'Laboratory Activity'),
        ('employees', 'Employee Analytics'),
        ('revenue', 'Revenue & Finance'),
    ]

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='saved_reports',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    report_type = models.CharField(
        max_length=50, choices=REPORT_TYPE_CHOICES, default='general'
    )
    time_range = models.CharField(max_length=50, default='30days')
    department = models.CharField(max_length=100, blank=True, default='')
    chart_type = models.CharField(
        max_length=20, choices=CHART_TYPE_CHOICES, default='line'
    )
    allowed_roles = models.JSONField(
        default=list, help_text='List of roles authorized to view this report'
    )
    created_by = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} (Facility {self.facility_id or 'Global'})"
