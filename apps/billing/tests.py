from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from core.models import Facility, User
from patients.models import Patient
from .models import Invoice, Payment


class BillingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = Facility.objects.create(
            name="Nairobi Medical Center",
            facility_type="hospital",
            registration_number="REG-BILL-001",
            email="billing@nairobihealth.com",
            phone="+254700112233"
        )
        self.user = User.objects.create_user(
            username="billing_admin",
            email="billing@nairobihealth.com",
            facility=self.facility,
            role="accountant"
        )
        self.client.force_authenticate(user=self.user)
        self.patient = Patient.objects.create(
            facility=self.facility,
            patient_id="PAT0001",
            first_name="Jane",
            last_name="Doe",
            gender="female",
            phone="+254711998877"
        )


    def test_create_invoice_with_string_patient_id(self):
        payload = {
            "patientId": "PAT0001",
            "facilityId": self.facility.id,
            "items": [
                {
                    "service": "Consultation Fee",
                    "amount": 2500
                },
                {
                    "service": "Lab Test",
                    "amount": 1500
                }
            ],
            "insurance": None
        }

        response = self.client.post(
            f"/api/billing/invoices/?facilityId={self.facility.id}/",
            payload,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertIn('data', response.data)
        self.assertEqual(response.data['data']['patientId'], "PAT0001")
        self.assertEqual(response.data['data']['facilityId'], self.facility.id)
        self.assertEqual(float(response.data['data']['total']), 4000.0)

    def test_list_invoices_filtered_by_facility(self):
        # Create an invoice for self.facility
        Invoice.objects.create(
            facility=self.facility,
            patient=self.patient,
            status="Pending"
        )

        # Create another facility and invoice
        other_fac = Facility.objects.create(
            name="Mombasa Clinic",
            facility_type="clinic",
            registration_number="REG-BILL-002",
            email="info@mombasaclinic.com",
            phone="+254722113344"
        )
        other_pat = Patient.objects.create(
            facility=other_fac,
            patient_id="PAT0002",
            first_name="John",
            last_name="Smith"
        )
        Invoice.objects.create(
            facility=other_fac,
            patient=other_pat,
            status="Pending"
        )

        response = self.client.get(f"/api/billing/invoices/?facilityId={self.facility.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        items = response.data['data']['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['facilityId'], self.facility.id)

    def test_record_payment_for_invoice(self):
        invoice = Invoice.objects.create(
            facility=self.facility,
            patient=self.patient,
            tax_rate=0,
            status="Pending"
        )

        payment_payload = {
            "amount": 2500,
            "method": "M-Pesa"
        }

        response = self.client.post(
            f"/api/billing/invoices/{invoice.id}/payments/?facilityId={self.facility.id}/",
            payment_payload,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['method'], "M-Pesa")

    def test_delete_invoice(self):
        invoice = Invoice.objects.create(
            facility=self.facility,
            patient=self.patient,
            status="Pending"
        )

        response = self.client.delete(f"/api/billing/invoices/{invoice.id}/?facilityId={self.facility.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Invoice.objects.filter(id=invoice.id).exists())

    def test_fetch_patient_pharmacy_charges(self):
        from pharmacy.models import Prescription, Drug
        Drug.objects.create(
            facility=self.facility,
            drug_id="D001",
            name="Amoxicillin 500mg",
            price=200.00
        )
        Prescription.objects.create(
            facility=self.facility,
            prescription_id="RX001",
            patient_id="PAT0001",
            doctor_id="DOC001",
            drugs=[
                {"id": "D001", "name": "Amoxicillin 500mg", "quantity": 2, "price": 200.00}
            ],
            status="Dispensed",
            date="2026-08-14"
        )

        response = self.client.get(
            f"/api/billing/patient-pharmacy-charges/?patientId=PAT0001&facilityId={self.facility.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['totalAmount'], 400.0)
        self.assertEqual(len(response.data['data']['items']), 1)
        self.assertEqual(response.data['data']['items'][0]['amount'], 400.0)

        # Test creating invoice with includePharmacy=True
        create_resp = self.client.post(
            f"/api/billing/invoices/?facilityId={self.facility.id}/",
            {
                "patientId": "PAT0001",
                "facilityId": self.facility.id,
                "items": [{"service": "Consultation", "amount": 1000}],
                "includePharmacy": True
            },
            format='json'
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(create_resp.data['data']['total']), 1400.0)

    def test_fetch_patient_lab_charges(self):
        from laboratory.models import LabTest, LabRequest
        import datetime
        test1 = LabTest.objects.create(
            facility=self.facility,
            test_id="L001",
            name="Full Blood Count",
            price=1500.00
        )
        LabRequest.objects.create(
            facility=self.facility,
            request_id="LR001",
            patient="Jane Doe",
            patient_id="PAT0001",
            test=test1,
            ordered_by_employee_id="E001",
            ordered_by="Dr. Smith",
            order_date=datetime.date.today(),
            status="Completed"
        )

        response = self.client.get(
            f"/api/billing/patient-lab-charges/?patientId=PAT0001&facilityId={self.facility.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['totalAmount'], 1500.0)
        self.assertEqual(len(response.data['data']['items']), 1)
        self.assertEqual(response.data['data']['items'][0]['amount'], 1500.0)

        # Test creating invoice with includeLabCharges=True
        create_resp = self.client.post(
            f"/api/billing/invoices/?facilityId={self.facility.id}/",
            {
                "patientId": "PAT0001",
                "facilityId": self.facility.id,
                "items": [{"service": "Consultation", "amount": 1000}],
                "includeLabCharges": True
            },
            format='json'
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(create_resp.data['data']['total']), 2500.0)

    def test_fetch_patient_radiology_charges(self):
        from radiology.models import ImagingStudy, ImagingRequest
        import datetime
        study = ImagingStudy.objects.create(
            facility=self.facility,
            study_id="R001",
            name="Chest X-Ray",
            price=3000.00
        )
        ImagingRequest.objects.create(
            facility=self.facility,
            request_id="IR001",
            patient="Jane Doe",
            patient_id="PAT0001",
            study=study,
            ordered_by_employee_id="E001",
            ordered_by="Dr. Smith",
            order_date=datetime.date.today(),
            status="Completed"
        )

        response = self.client.get(
            f"/api/billing/patient-radiology-charges/?patientId=PAT0001&facilityId={self.facility.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['totalAmount'], 3000.0)
        self.assertEqual(len(response.data['data']['items']), 1)
        self.assertEqual(response.data['data']['items'][0]['amount'], 3000.0)

        # Test creating invoice with includeRadiologyCharges=True
        create_resp = self.client.post(
            f"/api/billing/invoices/?facilityId={self.facility.id}/",
            {
                "patientId": "PAT0001",
                "facilityId": self.facility.id,
                "items": [{"service": "Consultation", "amount": 1000}],
                "includeRadiologyCharges": True
            },
            format='json'
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(create_resp.data['data']['total']), 4000.0)

    def test_mpesa_config_get_and_post(self):
        # GET default config
        get_res = self.client.get(f"/api/billing/mpesa-config/?facilityId={self.facility.id}")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertTrue(get_res.data['success'])
        self.assertEqual(get_res.data['data']['shortcode'], '')

        # UPDATE config
        update_payload = {
            "shortcode": "600000",
            "environment": "sandbox",
            "transaction_type": "CustomerBuyGoodsOnline",
            "passkey": "new_test_passkey_123"
        }
        post_res = self.client.post(
            f"/api/billing/mpesa-config/?facilityId={self.facility.id}",
            update_payload,
            format='json'
        )
        self.assertEqual(post_res.status_code, status.HTTP_200_OK)
        self.assertTrue(post_res.data['success'])
        self.assertEqual(post_res.data['data']['shortcode'], "600000")
        self.assertEqual(post_res.data['data']['transaction_type'], "CustomerBuyGoodsOnline")


    def test_mpesa_callback_and_query(self):
        from .models import MpesaTransaction
        invoice = Invoice.objects.create(
            facility=self.facility,
            patient=self.patient,
            status="Pending"
        )
        checkout_req_id = "ws_CO_30082026_TEST_12345"
        merchant_req_id = "12345-67890"

        txn = MpesaTransaction.objects.create(
            invoice=invoice,
            facility=self.facility,
            phone_number="254712345678",
            amount=1500.00,
            checkout_request_id=checkout_req_id,
            merchant_request_id=merchant_req_id,
            status="Pending"
        )

        # Simulate M-Pesa Callback from Safaricom
        callback_payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": merchant_req_id,
                    "CheckoutRequestID": checkout_req_id,
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1500.00},
                            {"Name": "MpesaReceiptNumber", "Value": "QGR99887766"},
                            {"Name": "TransactionDate", "Value": 20260830163000},
                            {"Name": "PhoneNumber", "Value": 254712345678}
                        ]
                    }
                }
            }
        }

        cb_res = self.client.post("/api/billing/mpesa/callback/", callback_payload, format='json')
        self.assertEqual(cb_res.status_code, status.HTTP_200_OK)

        txn.refresh_from_db()
        self.assertEqual(txn.status, "Completed")
        self.assertEqual(txn.mpesa_receipt_number, "QGR99887766")

        # Verify payment was automatically recorded & invoice marked paid
        invoice.refresh_from_db()
        self.assertEqual(Payment.objects.filter(invoice=invoice, method="M-Pesa").count(), 1)

        # Test STK Status Query Endpoint
        query_res = self.client.get(f"/api/billing/mpesa/query/?checkoutRequestId={checkout_req_id}")
        self.assertEqual(query_res.status_code, status.HTTP_200_OK)
        self.assertTrue(query_res.data['success'])
        self.assertEqual(query_res.data['data']['status'], "Completed")

