from django.db import models
from core.models import BaseModel, Facility

class Vendor(BaseModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='vendors')
    name = models.CharField(max_length=255)
    contact = models.CharField(max_length=100)
    email = models.EmailField()
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    total_orders = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class Supply(BaseModel):
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='supplies')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    stock = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=10)
    unit = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, related_name='supplies')
    last_ordered = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class Equipment(BaseModel):
    STATUS_CHOICES = (
        ('Operational', 'Operational'),
        ('Under Maintenance', 'Under Maintenance'),
        ('Out of Order', 'Out of Order'),
    )
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='equipments')
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Operational')
    last_maintenance = models.DateField(null=True, blank=True)
    next_maintenance = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=255)
    purchase_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class PurchaseOrder(BaseModel):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    )
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='purchase_orders')
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='purchase_orders')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Pending')
    order_date = models.DateField(auto_now_add=True)
    expected_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PO-{self.id} for {self.vendor.name}"

class PurchaseOrderItem(BaseModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    supply = models.ForeignKey(Supply, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.quantity} x {self.name}"
