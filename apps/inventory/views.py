import io
from django.shortcuts import get_object_or_404
from django.db.models import F
from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from core.models import Facility
from core.utils import check_module_permission
from .models import Vendor, Supply, Equipment, PurchaseOrder, PurchaseOrderItem
from .serializers import (
    VendorSerializer,
    SupplySerializer,
    EquipmentSerializer,
    PurchaseOrderSerializer
)


class RbacInventoryMixin:
    """Mixin to enforce the 'inventory' module permission."""
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user and request.user.is_authenticated:
            check_module_permission(request.user, 'inventory')

class VendorViewSet(RbacInventoryMixin, viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        facility_id = self.request.query_params.get('facility')
        if facility_id:
            return Vendor.objects.filter(facility_id=facility_id)
        return Vendor.objects.none()

    def perform_create(self, serializer):
        facility_id = self.request.query_params.get('facility')
        facility = get_object_or_404(Facility, pk=facility_id)
        serializer.save(facility=facility)

class EquipmentViewSet(RbacInventoryMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        facility_id = self.request.query_params.get('facility')
        if facility_id:
            return Equipment.objects.filter(facility_id=facility_id)
        return Equipment.objects.none()

    def perform_create(self, serializer):
        facility_id = self.request.query_params.get('facility')
        facility = get_object_or_404(Facility, pk=facility_id)
        serializer.save(facility=facility)

class PurchaseOrderViewSet(RbacInventoryMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        facility_id = self.request.query_params.get('facility')
        if facility_id:
            return PurchaseOrder.objects.filter(facility_id=facility_id)
        return PurchaseOrder.objects.none()

    def perform_create(self, serializer):
        facility_id = self.request.query_params.get('facility')
        facility = get_object_or_404(Facility, pk=facility_id)
        serializer.save(facility=facility)

class SupplyViewSet(RbacInventoryMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SupplySerializer

    def get_queryset(self):
        facility_id = self.request.query_params.get('facility')
        if facility_id:
            return Supply.objects.filter(facility_id=facility_id)
        return Supply.objects.none()

    def perform_create(self, serializer):
        facility_id = self.request.query_params.get('facility')
        facility = get_object_or_404(Facility, pk=facility_id)
        serializer.save(facility=facility)

    @action(detail=False, methods=['post'])
    def reorder_low_stock(self, request):
        facility_id = request.query_params.get('facility')
        if not facility_id:
            return Response({"error": "Facility ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        low_stock_supplies = Supply.objects.filter(facility_id=facility_id, stock__lt=F('min_stock'))
        
        if not low_stock_supplies.exists():
            return Response({"message": "No supplies need reordering"}, status=status.HTTP_200_OK)
        
        # Group by vendor
        vendors_supplies = {}
        for supply in low_stock_supplies:
            if not supply.vendor:
                continue
            if supply.vendor not in vendors_supplies:
                vendors_supplies[supply.vendor] = []
            vendors_supplies[supply.vendor].append(supply)
            
        orders_created = 0
        emails_sent = 0
        
        for vendor, supplies in vendors_supplies.items():
            # Create a PO
            total = sum([(s.min_stock * 2 - s.stock) * s.price for s in supplies]) # Order enough to double min_stock
            po = PurchaseOrder.objects.create(
                facility_id=facility_id,
                vendor=vendor,
                total=total,
                status='Pending'
            )
            
            items_text = []
            for s in supplies:
                qty = s.min_stock * 2 - s.stock
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    supply=s,
                    name=s.name,
                    quantity=qty,
                    price=s.price
                )
                items_text.append(f"- {qty} x {s.name} @ {s.price} each")
                
            # Send Email
            if vendor.email:
                subject = f"Purchase Order PO-{po.id} from Afyora"
                body = f"Hello {vendor.name},\n\nPlease process the following order:\n" + "\n".join(items_text) + f"\n\nTotal: {total}\n\nThank you."
                try:
                    send_mail(
                        subject,
                        body,
                        settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else 'noreply@afyora.com',
                        [vendor.email],
                        fail_silently=True
                    )
                    emails_sent += 1
                except Exception:
                    pass
            
            orders_created += 1

        return Response({
            "message": f"Successfully created {orders_created} purchase orders and sent {emails_sent} emails."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def supply_report(self, request):
        facility_id = request.query_params.get('facility')
        if not facility_id:
            return Response({"error": "Facility ID required"}, status=status.HTTP_400_BAD_REQUEST)
        
        supplies = Supply.objects.filter(facility_id=facility_id)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        elements.append(Paragraph("Supply Inventory Report", styles['Title']))
        elements.append(Spacer(1, 12))
        
        data = [["ID", "Name", "Category", "Stock", "Min Stock", "Price", "Vendor"]]
        for s in supplies:
            data.append([
                str(s.id),
                s.name,
                s.category,
                str(s.stock),
                str(s.min_stock),
                f"${s.price}",
                s.vendor.name if s.vendor else "N/A"
            ])
            
        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(t)
        doc.build(elements)
        
        buffer.seek(0)
        return HttpResponse(buffer, content_type='application/pdf')

