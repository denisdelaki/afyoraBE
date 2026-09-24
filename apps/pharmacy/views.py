import io
from datetime import date

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.http import Http404, HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable

from core.models import Facility, User
from core.knhts import KnhtsServiceError, search_concepts
from core.utils import check_module_permission, send_transactional_email
from .models import Drug, DrugCategory, DrugPurchaseOrder, DrugPurchaseOrderItem, Prescription
from .serializers import (
    DrugCategorySerializer, DrugPurchaseOrderSerializer,
    DrugSerializer, PrescriptionSerializer,
)


class FacilityScopedPharmacyViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated]
	MODULE_KEY = 'pharmacy'

	def initial(self, request, *args, **kwargs):
		super().initial(request, *args, **kwargs)
		if request.user and request.user.is_authenticated:
			check_module_permission(request.user, self.MODULE_KEY, request=request)


	@staticmethod
	def _parse_facility_id(value, error_message):
		if isinstance(value, str):
			value = value.strip().rstrip('/')

		try:
			return int(value)
		except (TypeError, ValueError):
			raise ValidationError({'facilityId': error_message})

	def _get_requested_facility_id(self):
		facility_id = self.request.query_params.get('facilityId')
		if facility_id is None:
			facility_id = self.request.query_params.get('facility_id')

		if facility_id is None:
			return None

		return self._parse_facility_id(
			facility_id,
			'facilityId must be a valid integer.',
		)

	def _get_target_facility(self):
		user = self.request.user
		requested_facility_id = self._get_requested_facility_id()

		if user.facility_id:
			if (
				requested_facility_id is not None
				and requested_facility_id != user.facility_id
			):
				raise PermissionDenied('You cannot access pharmacy data from another facility.')
			return user.facility

		if user.role == 'admin':
			if requested_facility_id is None:
				raise ValidationError(
					{'facilityId': 'facilityId query param is required for admin users.'}
				)
			return Facility.objects.filter(id=requested_facility_id).first()

		raise PermissionDenied('Your account is not assigned to a facility.')


class DrugCategoryViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = DrugCategorySerializer
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = []
	search_fields = ['name', 'description']
	ordering = ['name']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		return DrugCategory.objects.filter(facility=facility, is_active=True)

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				'items': serializer.data,
				'count': queryset.count(),
			},
			status=status.HTTP_200_OK,
		)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		category = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if category.facility_id != facility.id:
			raise PermissionDenied('You cannot modify categories from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete categories from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


class DrugViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = DrugSerializer
	lookup_field = 'drug_id'
	lookup_url_kwarg = 'drug_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['category', 'manufacturer']
	search_fields = ['drug_id', 'name', 'category__name', 'manufacturer']
	ordering = ['-created_at']

	@action(detail=False, methods=['get'], url_path='terminology-search')
	def terminology_search(self, request):
		search = request.query_params.get('search', '').strip()
		if len(search) < 2:
			raise ValidationError({'search': 'Enter at least 2 characters.'})

		try:
			concepts = search_concepts(
				search,
				valueset_url=settings.KNHTS_DRUG_VALUESET_URL,
			)
		except KnhtsServiceError:
			return Response(
				{
					'data': [],
					'source': 'unavailable',
					'detail': 'Drug terminology is temporarily unavailable. Enter an uncoded drug name to continue.',
				},
				status=status.HTTP_503_SERVICE_UNAVAILABLE,
			)

		return Response({'data': concepts, 'source': 'knhts'})

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		return Drug.objects.filter(facility=facility, is_active=True)

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				'items': serializer.data,
				'count': queryset.count(),
			},
			status=status.HTTP_200_OK,
		)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		drug = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if drug.facility_id != facility.id:
			raise PermissionDenied('You cannot modify drugs from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete drugs from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])


class PrescriptionViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = PrescriptionSerializer
	lookup_field = 'prescription_id'
	lookup_url_kwarg = 'prescription_id'
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']
	filterset_fields = ['status', 'date']
	search_fields = ['prescription_id', 'patient_id', 'doctor_id', 'status']
	ordering = ['-date', '-created_at']

	def _query_prescriptions(self, include_inactive=False):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		queryset = Prescription.objects.filter(facility=facility)
		if not include_inactive:
			queryset = queryset.filter(is_active=True)

		return queryset

	def get_object(self):
		include_inactive = self.action == 'destroy'
		queryset = self.filter_queryset(
			self._query_prescriptions(include_inactive=include_inactive)
		)
		lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
		lookup_value = self.kwargs.get(lookup_url_kwarg)

		instance = None
		if isinstance(lookup_value, str) and lookup_value.isdigit():
			instance = queryset.filter(pk=int(lookup_value)).first()

		if instance is None:
			instance = queryset.filter(**{self.lookup_field: lookup_value}).first()

		if instance is None:
			raise Http404

		self.check_object_permissions(self.request, instance)
		return instance

	def get_queryset(self):
		return self._query_prescriptions(include_inactive=False)

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				'items': serializer.data,
				'count': queryset.count(),
			},
			status=status.HTTP_200_OK,
		)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_update(self, serializer):
		prescription = self.get_object()
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if prescription.facility_id != facility.id:
			raise PermissionDenied('You cannot modify prescriptions from another facility.')

		serializer.save()

	def perform_destroy(self, instance):
		facility = self._get_target_facility()

		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		if instance.facility_id != facility.id:
			raise PermissionDenied('You cannot delete prescriptions from another facility.')

		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])

	@action(detail=True, methods=['post', 'patch'])
	def dispense(self, request, prescription_id=None):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})

		prescription = self.get_object()
		if prescription.facility_id != facility.id:
			raise PermissionDenied('You cannot dispense prescriptions from another facility.')

		with transaction.atomic():
			locked_prescription = (
				Prescription.objects.select_for_update()
				.filter(pk=prescription.pk, facility_id=facility.id)
				.first()
			)

			if locked_prescription is None:
				raise Http404

			if locked_prescription.status == 'Dispensed':
				serializer = self.get_serializer(locked_prescription)
				return Response(serializer.data, status=status.HTTP_200_OK)

			today = timezone.localdate()
			drug_updates = []
			for index, item in enumerate(locked_prescription.drugs or []):
				if not isinstance(item, dict):
					raise ValidationError(
						{'drugs': f'Invalid drug payload at index {index}.'}
					)

				drug_id = str(item.get('id') or '').strip()
				drug_name = str(item.get('name') or '').strip()
				quantity = item.get('quantity')

				try:
					quantity = int(quantity)
				except (TypeError, ValueError):
					raise ValidationError(
						{'drugs': f'Invalid quantity for drug at index {index}.'}
					)

				if quantity <= 0:
					raise ValidationError(
						{'drugs': f'Quantity must be greater than zero at index {index}.'}
					)

				drug_qs = Drug.objects.select_for_update().filter(
					facility_id=facility.id,
					is_active=True,
				)

				drug = None
				if drug_id:
					drug = drug_qs.filter(drug_id=drug_id).first()

				if drug is None and drug_name:
					drug = drug_qs.filter(name__iexact=drug_name).first()

				if drug is None:
					raise ValidationError(
						{'drugs': f'Drug not found at index {index}.'}
					)

				if drug.expiry_date and drug.expiry_date < today:
					raise ValidationError(
						{'drugs': f'Drug {drug.name} is expired and cannot be dispensed.'}
					)

				if drug.stock < quantity:
					raise ValidationError(
						{
							'drugs': (
								f'Insufficient stock for {drug.name}. '
								f'Available: {drug.stock}, requested: {quantity}.'
							)
						}
					)

				drug_updates.append((drug, quantity))

			for drug, quantity in drug_updates:
				drug.stock -= quantity
				drug.save(update_fields=['stock', 'updated_at'])

			locked_prescription.status = 'Dispensed'
			locked_prescription.save(update_fields=['status', 'updated_at'])

		serializer = self.get_serializer(locked_prescription)
		return Response(serializer.data, status=status.HTTP_200_OK)


class DrugPurchaseOrderViewSet(FacilityScopedPharmacyViewSet):
	serializer_class = DrugPurchaseOrderSerializer
	http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

	def get_queryset(self):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		return DrugPurchaseOrder.objects.filter(facility=facility, is_active=True).prefetch_related('items', 'vendor')

	def list(self, request, *args, **kwargs):
		queryset = self.filter_queryset(self.get_queryset())
		serializer = self.get_serializer(queryset, many=True)
		return Response({'items': serializer.data, 'count': queryset.count()}, status=status.HTTP_200_OK)

	def perform_create(self, serializer):
		facility = self._get_target_facility()
		if facility is None:
			raise ValidationError({'facilityId': 'Facility not found.'})
		serializer.save(facility=facility)

	def perform_destroy(self, instance):
		instance.is_active = False
		instance.save(update_fields=['is_active', 'updated_at'])

	def _build_pdf(self, po):
		"""Generate a PDF BytesIO for the given DrugPurchaseOrder."""
		buffer = io.BytesIO()
		doc = SimpleDocTemplate(
			buffer, pagesize=letter,
			rightMargin=0.75 * inch, leftMargin=0.75 * inch,
			topMargin=0.75 * inch, bottomMargin=0.75 * inch,
		)
		styles = getSampleStyleSheet()
		elements = []

		# Header
		elements.append(Paragraph("DRUG PURCHASE ORDER", styles['Title']))
		elements.append(Spacer(1, 6))
		elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2563EB")))
		elements.append(Spacer(1, 12))

		# Meta info table
		meta = [
			["PO Number:", po.po_number, "Status:", po.status],
			["Order Date:", str(po.order_date), "Expected Date:", str(po.expected_date or "TBD")],
			["Vendor:", po.vendor.name if po.vendor else "N/A", "Vendor Email:", po.vendor.email if po.vendor else "N/A"],
			["Facility:", str(po.facility.name if hasattr(po.facility, 'name') else po.facility_id), "", ""],
		]
		meta_table = Table(meta, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 2*inch])
		meta_table.setStyle(TableStyle([
			('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
			('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
			('FONTSIZE', (0, 0), (-1, -1), 9),
			('BOTTOMPADDING', (0, 0), (-1, -1), 4),
			('TOPPADDING', (0, 0), (-1, -1), 4),
		]))
		elements.append(meta_table)
		elements.append(Spacer(1, 16))

		# Items table
		elements.append(Paragraph("Order Items", styles['Heading2']))
		elements.append(Spacer(1, 6))
		header = [["#", "Drug Name", "Qty", "Unit Price (Kes)", "Total (Kes)"]]
		rows = []
		for i, item in enumerate(po.items.all(), 1):
			rows.append([
				str(i),
				item.drug_name,
				str(item.quantity),
				f"{item.unit_price:,.2f}",
				f"{item.total_price:,.2f}",
			])
		items_data = header + rows + [["", "", "", "TOTAL", f"Kes {po.total:,.2f}"]]

		items_table = Table(items_data, colWidths=[0.4*inch, 3*inch, 0.6*inch, 1.5*inch, 1.5*inch])
		items_table.setStyle(TableStyle([
			('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2563EB")),
			('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
			('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
			('FONTSIZE', (0, 0), (-1, -1), 9),
			('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor("#F1F5F9")]),
			('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
			('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
			('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
			('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor("#2563EB")),
			('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#2563EB")),
			('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor("#E2E8F0")),
			('TOPPADDING', (0, 0), (-1, -1), 5),
			('BOTTOMPADDING', (0, 0), (-1, -1), 5),
		]))
		elements.append(items_table)

		if po.notes:
			elements.append(Spacer(1, 16))
			elements.append(Paragraph("Notes", styles['Heading2']))
			elements.append(Paragraph(po.notes, styles['Normal']))

		elements.append(Spacer(1, 24))
		elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
		elements.append(Spacer(1, 6))
		elements.append(Paragraph(
			f"Generated by Afyora HMS on {date.today().strftime('%d %B %Y')}",
			styles['Normal']
		))

		doc.build(elements)
		buffer.seek(0)
		return buffer

	@action(detail=True, methods=['get'])
	def pdf(self, request, pk=None):
		"""Download the purchase order as a PDF."""
		po = self.get_object()
		buffer = self._build_pdf(po)
		response = HttpResponse(buffer, content_type='application/pdf')
		response['Content-Disposition'] = f'attachment; filename="PO-{po.po_number}.pdf"'
		return response

	@action(detail=True, methods=['get'])
	def recipients(self, request, pk=None):
		"""Retrieve vendor email and auto-detected CC emails (facility admin & pharmacists)."""
		po = self.get_object()

		staff_emails = list(
			User.objects.filter(
				facility=po.facility,
				role__in=['facility_admin', 'pharmacist'],
				is_active=True,
			).exclude(email='').values_list('email', flat=True).distinct()
		)

		user_email = getattr(request.user, 'email', '')
		if user_email and user_email not in staff_emails:
			staff_emails.append(user_email)

		vendor_email = po.vendor.email if po.vendor else ''
		if vendor_email and vendor_email in staff_emails:
			staff_emails.remove(vendor_email)

		return Response({
			'vendor_email': vendor_email,
			'cc_emails': staff_emails,
		}, status=status.HTTP_200_OK)

	@action(detail=True, methods=['post'])
	def send_email(self, request, pk=None):
		"""Email the PO PDF to the vendor and CC facility contacts."""
		po = self.get_object()

		if not po.vendor or not po.vendor.email:
			return Response({'error': 'Vendor has no email address configured.'}, status=status.HTTP_400_BAD_REQUEST)

		buffer = self._build_pdf(po)
		pdf_bytes = buffer.read()

		subject = f"Purchase Order {po.po_number} from Afyora HMS"
		body = (
			f"Dear {po.vendor.name},\n\n"
			f"Please find attached Purchase Order {po.po_number} for your review and processing.\n\n"
			f"Order Date: {po.order_date}\n"
			f"Expected Delivery: {po.expected_date or 'TBD'}\n"
			f"Total Amount: Kes {po.total:,.2f}\n\n"
			f"Kindly acknowledge receipt of this order.\n\n"
			f"Regards,\nAfyora HMS"
		)

		# Collect CC recipients from payload
		input_cc = request.data.get('cc_emails', [])
		if isinstance(input_cc, str):
			input_cc = [input_cc]

		# Auto-fetch facility admin and pharmacist emails
		auto_cc = list(
			User.objects.filter(
				facility=po.facility,
				role__in=['facility_admin', 'pharmacist'],
				is_active=True,
			).exclude(email='').values_list('email', flat=True).distinct()
		)

		all_cc = set(input_cc) | set(auto_cc)
		if request.user and getattr(request.user, 'email', None):
			all_cc.add(request.user.email)

		all_cc.discard(po.vendor.email)
		final_cc = [e for e in all_cc if e and '@' in e]

		try:
			send_transactional_email(
				to_email=po.vendor.email,
				subject=subject,
				text=body,
				cc_emails=final_cc,
				attachments=[{
					'name': f"PO-{po.po_number}.pdf",
					'bytes': pdf_bytes,
				}],
			)

			po.email_sent = True
			po.save(update_fields=['email_sent', 'updated_at'])

			cc_msg = f" (CC: {', '.join(final_cc)})" if final_cc else ""
			return Response({'message': f'Purchase order emailed to {po.vendor.email}{cc_msg}.'}, status=status.HTTP_200_OK)
		except Exception as e:
			return Response({'error': f'Failed to send email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
