# billing/models.py
import re
from django.db import models
from django.db.models import Sum
from core.models import Facility
from patients.models import Patient


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('Paid', 'Paid'),
        ('Pending', 'Pending'),
        ('Overdue', 'Overdue'),
    ]

    id = models.CharField(primary_key=True, max_length=20, editable=False)
    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True
    )
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name='invoices'
    )
    date = models.DateField(auto_now_add=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.id:
            last = Invoice.objects.order_by('-created_at').first()
            next_num = 1
            if last and last.id:
                try:
                    nums = re.findall(r'\d+', last.id)
                    if nums:
                        next_num = int(nums[-1]) + 1
                except ValueError:
                    pass
            self.id = f'INV{next_num:04d}'
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return self.items.aggregate(s=Sum('amount'))['s'] or 0

    @property
    def tax(self):
        return round(float(self.subtotal) * (float(self.tax_rate) / 100), 2)

    @property
    def total(self):
        return float(self.subtotal) + float(self.tax)

    def recalc_status(self):
        paid = self.payments.filter(status='Completed').aggregate(
            s=Sum('amount')
        )['s'] or 0
        if float(paid) >= float(self.total):
            self.status = 'Paid'
        self.save(update_fields=['status'])


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    service = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)


class InsuranceInfo(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='insurance')
    company = models.CharField(max_length=255)
    coverage = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    claim = models.CharField(max_length=100, blank=True, default='')


class Payment(models.Model):
    STATUS_CHOICES = [
        ('Completed', 'Completed'),
        ('Pending', 'Pending'),
        ('Failed', 'Failed'),
    ]

    id = models.CharField(primary_key=True, max_length=20, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=50)
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Completed')

    def save(self, *args, **kwargs):
        if not self.id:
            last = Payment.objects.order_by('-id').first()
            next_num = 1
            if last and last.id:
                try:
                    nums = re.findall(r'\d+', last.id)
                    if nums:
                        next_num = int(nums[-1]) + 1
                except ValueError:
                    pass
            self.id = f'PMT{next_num:04d}'
        super().save(*args, **kwargs)