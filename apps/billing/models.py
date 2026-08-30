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


class MpesaConfig(models.Model):
    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ]
    TRANSACTION_TYPE_CHOICES = [
        ('CustomerPayBillOnline', 'Paybill'),
        ('CustomerBuyGoodsOnline', 'Till Number'),
    ]


    facility = models.OneToOneField(
        Facility, on_delete=models.CASCADE, related_name='mpesa_config'
    )
    shortcode = models.CharField(max_length=20, default='')
    passkey = models.CharField(
        max_length=255,
        blank=True,
        default='bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
    )
    consumer_key = models.CharField(max_length=255, blank=True, default='')
    consumer_secret = models.CharField(max_length=255, blank=True, default='')
    environment = models.CharField(max_length=20, choices=ENVIRONMENT_CHOICES, default='sandbox')
    transaction_type = models.CharField(
        max_length=50, choices=TRANSACTION_TYPE_CHOICES, default='CustomerPayBillOnline'
    )
    account_reference_prefix = models.CharField(max_length=50, default='AfyoraHMS')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"M-Pesa Config for {self.facility.name} ({self.shortcode})"


class MpesaTransaction(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Cancelled', 'Cancelled'),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='mpesa_transactions', null=True, blank=True
    )
    subscription_payment = models.ForeignKey(
        'core.FacilitySubscriptionPayment',
        on_delete=models.CASCADE,
        related_name='mpesa_transactions',
        null=True,
        blank=True
    )
    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name='mpesa_transactions', null=True, blank=True
    )

    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    checkout_request_id = models.CharField(max_length=100, unique=True)
    merchant_request_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    result_code = models.IntegerField(null=True, blank=True)
    result_desc = models.TextField(blank=True, null=True)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    transaction_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"M-Pesa Txn {self.checkout_request_id} - {self.phone_number} ({self.status})"