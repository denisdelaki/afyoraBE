from django.db import models

from core.models import BaseModel, Facility


class ImagingStudy(BaseModel):
    """Catalogue of imaging/radiology study types offered by a facility."""

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='imaging_studies',
    )
    study_id = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, blank=True)
    modality = models.CharField(max_length=80, blank=True)  # e.g. X-Ray, CT Scan, MRI
    body_part = models.CharField(max_length=80, blank=True)  # e.g. Thorax, Abdomen
    duration = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['name']
        unique_together = ('facility', 'study_id')
        indexes = [
            models.Index(fields=['facility', 'study_id']),
            models.Index(fields=['facility', 'name']),
            models.Index(fields=['facility', 'category']),
        ]

    def __str__(self):
        return f"{self.study_id} - {self.name}"


class ImagingRequest(BaseModel):
    """A request for an imaging/radiology study for a patient."""

    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Approved', 'Approved'),
    )

    PRIORITY_CHOICES = (
        ('Routine', 'Routine'),
        ('Urgent', 'Urgent'),
        ('STAT', 'STAT'),
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='imaging_requests',
    )
    request_id = models.CharField(max_length=20)
    patient = models.CharField(max_length=255)
    patient_id = models.CharField(max_length=30)
    study = models.ForeignKey(
        ImagingStudy,
        on_delete=models.PROTECT,
        related_name='requests',
    )
    ordered_by_employee_id = models.CharField(max_length=50)
    ordered_by = models.CharField(max_length=150)
    order_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Routine')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-order_date', '-created_at']
        unique_together = ('facility', 'request_id')
        indexes = [
            models.Index(fields=['facility', 'request_id']),
            models.Index(fields=['facility', 'status']),
            models.Index(fields=['facility', 'order_date']),
            models.Index(fields=['facility', 'patient_id']),
        ]

    def __str__(self):
        return f"{self.request_id} - {self.patient}"


class ImagingReport(BaseModel):
    """A radiologist's report for a completed imaging request."""

    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Finalized', 'Finalized'),
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='imaging_reports',
    )
    report_id = models.CharField(max_length=20)
    request = models.OneToOneField(
        ImagingRequest,
        on_delete=models.CASCADE,
        related_name='report',
    )
    radiologist = models.CharField(max_length=150)
    scan_date = models.DateField()
    findings = models.TextField(blank=True)
    impression = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')

    class Meta:
        ordering = ['-scan_date', '-created_at']
        unique_together = ('facility', 'report_id')
        indexes = [
            models.Index(fields=['facility', 'report_id']),
            models.Index(fields=['facility', 'status']),
        ]

    def __str__(self):
        return f"{self.report_id} - {self.request.patient}"


class ImagingImage(BaseModel):
    """An image uploaded for an imaging request."""

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='imaging_images',
    )
    request = models.ForeignKey(
        ImagingRequest,
        on_delete=models.CASCADE,
        related_name='images',
    )
    name = models.CharField(max_length=255)
    url = models.TextField()
    source = models.CharField(max_length=50, default='uploaded')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['facility', 'request']),
        ]

    def __str__(self):
        return f"Image for {self.request.request_id} - {self.name}"


