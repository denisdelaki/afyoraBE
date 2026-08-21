from rest_framework import serializers
from .models import Vendor, Supply, Equipment, PurchaseOrder, PurchaseOrderItem

class VendorSerializer(serializers.ModelSerializer):
    totalOrders = serializers.IntegerField(source='total_orders', read_only=True)

    class Meta:
        model = Vendor
        fields = ['id', 'name', 'contact', 'email', 'rating', 'totalOrders']

class SupplySerializer(serializers.ModelSerializer):
    minStock = serializers.IntegerField(source='min_stock')
    lastOrdered = serializers.DateField(source='last_ordered', read_only=True)
    vendorName = serializers.CharField(source='vendor.name', read_only=True)

    class Meta:
        model = Supply
        fields = ['id', 'name', 'category', 'stock', 'minStock', 'unit', 'price', 'vendor', 'vendorName', 'lastOrdered']

class EquipmentSerializer(serializers.ModelSerializer):
    lastMaintenance = serializers.DateField(source='last_maintenance', required=False, allow_null=True)
    nextMaintenance = serializers.DateField(source='next_maintenance', required=False, allow_null=True)
    purchaseDate = serializers.DateField(source='purchase_date', required=False, allow_null=True)

    class Meta:
        model = Equipment
        fields = ['id', 'name', 'category', 'status', 'lastMaintenance', 'nextMaintenance', 'location', 'purchaseDate']

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'name', 'quantity', 'price']

class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    vendorName = serializers.CharField(source='vendor.name', read_only=True)
    orderDate = serializers.DateField(source='order_date', read_only=True)
    expectedDate = serializers.DateField(source='expected_date', required=False, allow_null=True)

    class Meta:
        model = PurchaseOrder
        fields = ['id', 'vendor', 'vendorName', 'items', 'total', 'status', 'orderDate', 'expectedDate']
