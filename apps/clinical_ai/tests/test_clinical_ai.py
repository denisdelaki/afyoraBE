from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.exceptions import ValidationError

from core.models import Facility, User
from patients.models import Patient
from clinical_ai.models import (
    ClinicalAIConsultation,
    ClinicalAIRecommendation,
    ClinicalAIFeedback,
    ClinicalAIAuditEvent,
    ClinicalAIModelVersion,
)
from clinical_ai.serializers import ClinicalAIConsultationRequestSerializer


from clinical_ai.services.ai_gateway import call_clinical_ai_analysis, ClinicalAIServiceError
from clinical_ai.services.consultation_service import build_analysis_payload


def analysis_result():
    return {
        'supported_diagnosis': 'Provisional assessment; clinician review required.',
        'possible_disease': ['Possible condition'],
        'drugs_admissible': [],
        'further_labs_to_be_done': ['Suggested investigation'],
        'triage': {
            'level': 'urgent',
            'urgent_care_recommended': True,
            'reasons': ['oxygen_saturation: 80 % meets an urgent screening threshold.'],
            'unassessed_vitals': ['respiratory_rate'],
            'recommendation': 'Urgent in-person clinical assessment is recommended now. Do not delay care or wait for AI advice.',
            'requires_human_review': True,
            'rule_set': 'adult-vital-screening-v1',
        },
    }


@override_settings(CLINICAL_AI_BASE_URL='https://clinical.example', CLINICAL_AI_TOKEN='test-token', CLINICAL_AI_TIMEOUT=45)
class ClinicalAIGatewayTests(SimpleTestCase):
    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_documented_endpoint_and_bearer_token(self, post):
        post.return_value = Mock(status_code=200, json=Mock(return_value=analysis_result()))
        result = call_clinical_ai_analysis({'symptoms': ['fever']})
        self.assertEqual(result['supported_diagnosis'], analysis_result()['supported_diagnosis'])
        self.assertEqual(result['triage']['level'], 'urgent')
        self.assertTrue(result['triage']['requires_human_review'])
        self.assertEqual(post.call_args.args[0], 'https://clinical.example/api/clinical-ai/analyze/')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer test-token')
        self.assertEqual(post.call_args.kwargs['headers']['X-Request-ID'], result['request_id'])
        self.assertEqual(post.call_args.kwargs['json'], {'symptoms': ['fever']})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.kwargs['timeout'], 45)

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_failures_are_not_successful_assessments(self, post):
        for upstream, downstream in [(400, 400), (401, 503), (405, 502), (415, 502), (429, 429), (502, 502), (503, 503), (504, 504), (302, 502)]:
            with self.subTest(upstream=upstream):
                post.return_value = Mock(status_code=upstream)
                with self.assertRaises(ClinicalAIServiceError) as raised:
                    call_clinical_ai_analysis({})
                self.assertEqual(raised.exception.status_code, downstream)
                self.assertNotIn('clinical_summary', raised.exception.detail)

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_invalid_response_fails_closed(self, post):
        invalid_responses = [
            {**analysis_result(), 'extra_field': 'not allowed'},
            {**analysis_result(), 'triage': {**analysis_result()['triage'], 'requires_human_review': False}},
            {**analysis_result(), 'triage': {**analysis_result()['triage'], 'level': 'unknown'}},
            {**analysis_result(), 'triage': {**analysis_result()['triage'], 'reasons': [42]}},
        ]
        for invalid in invalid_responses:
            with self.subTest(invalid=invalid):
                post.return_value = Mock(status_code=200, json=Mock(return_value=invalid))
                with self.assertLogs('clinical_ai', level='WARNING') as captured:
                    with self.assertRaises(ClinicalAIServiceError) as raised:
                        call_clinical_ai_analysis({})
                self.assertEqual(raised.exception.status_code, 502)
                diagnostic = '\n'.join(captured.output)
                self.assertIn(raised.exception.request_id, diagnostic)
                self.assertNotIn(str(invalid), diagnostic)

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_upstream_502_is_distinct_from_local_validation_failure(self, post):
        post.return_value = Mock(status_code=502, text='Private provider diagnostic and patient details')
        with self.assertRaises(ClinicalAIServiceError) as raised:
            call_clinical_ai_analysis({})
        self.assertEqual(raised.exception.detail['error']['code'], 'clinical_ai_provider_failure')
        self.assertEqual(str(raised.exception.detail['error']['upstream_status']), '502')
        self.assertNotIn('Private provider diagnostic', str(raised.exception.detail))
        post.return_value = Mock(status_code=200, json=Mock(return_value={}))
        with self.assertRaises(ClinicalAIServiceError) as raised:
            call_clinical_ai_analysis({})
        self.assertEqual(raised.exception.detail['error']['code'], 'clinical_ai_invalid_response')

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_known_standalone_error_codes_are_preserved_without_raw_messages(self, post):
        for upstream_code, expected_code in (
            ('ai_provider_error', 'clinical_ai_provider_failure'),
            ('ai_invalid_response', 'clinical_ai_invalid_model_response'),
            ('ai_analysis_failed', 'clinical_ai_analysis_failed'),
        ):
            with self.subTest(upstream_code=upstream_code):
                post.return_value = Mock(status_code=502, json=Mock(return_value={
                    'error': {'code': upstream_code, 'message': 'Private clinical data or credentials'},
                }))
                with self.assertRaises(ClinicalAIServiceError) as raised:
                    call_clinical_ai_analysis({})
                error = raised.exception.detail['error']
                self.assertEqual(error['code'], expected_code)
                self.assertEqual(error['upstream_code'], upstream_code)
                self.assertNotIn('Private clinical data', str(raised.exception.detail))

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_unknown_or_malformed_upstream_error_is_not_forwarded(self, post):
        for body in ({'error': {'code': 'private_patient_reference', 'message': 'Private data'}}, [], {'error': {'code': []}}):
            post.return_value = Mock(status_code=502, json=Mock(return_value=body))
            with self.assertRaises(ClinicalAIServiceError) as raised:
                call_clinical_ai_analysis({})
            self.assertNotIn('upstream_code', raised.exception.detail['error'])
            self.assertNotIn('private_patient_reference', str(raised.exception.detail))

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_timeout_and_connection_failure(self, post):
        for error, expected in [(requests.Timeout(), 504), (requests.ConnectionError(), 502)]:
            post.side_effect = error
            with self.assertRaises(ClinicalAIServiceError) as raised:
                call_clinical_ai_analysis({})
            self.assertEqual(raised.exception.status_code, expected)

    @override_settings(CLINICAL_AI_TOKEN='')
    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_missing_token_does_not_make_request(self, post):
        with self.assertRaises(ClinicalAIServiceError) as raised:
            call_clinical_ai_analysis({})
        self.assertEqual(raised.exception.status_code, 503)
        post.assert_not_called()

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_malformed_or_incomplete_json_fails_closed(self, post):
        for value in [{}, [], {'clinical_summary': 'Unvalidated'}]:
            post.return_value = Mock(status_code=200, json=Mock(return_value=value))
            with self.assertRaises(ClinicalAIServiceError):
                call_clinical_ai_analysis({})
        post.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError('Invalid JSON')))
        with self.assertRaises(ClinicalAIServiceError):
            call_clinical_ai_analysis({})

    @override_settings(CLINICAL_AI_BASE_URL='http://clinical.example')
    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_remote_http_does_not_send_token_or_patient_data(self, post):
        with self.assertRaises(ClinicalAIServiceError):
            call_clinical_ai_analysis({})
        post.assert_not_called()

    def test_payload_uses_documented_fields_and_excludes_identifiers(self):
        patient = Mock(age=32, gender='female')
        context = {
            'demographics': {'patient_id': 'PAT-001', 'date_of_birth': '1994-01-01'},
            'active_problems': [{'display': 'Example condition', 'code': 'example'}],
            'allergies': [{'allergen_name': 'Example allergen', 'reaction': 'Rash', 'severity': 'Mild'}],
            'previous_diagnoses': [{'diagnosis': 'Example prior diagnosis', 'doctor': 'private-doctor'}],
            'current_medications': [{'prescription_id': 'RX-private', 'drugs': [{'name': 'Example drug', 'dosage': 'Example dose'}]}],
            'recent_lab_results': [{'lab_id': 'LAB-private', 'test_name': 'Example test', 'parameters': [{'name': 'Example parameter', 'value': 1}]}],
            'recent_imaging_reports': [{'report_id': 'IMG-private', 'findings': 'Example finding'}],
        }
        payload = build_analysis_payload(patient, {
            'symptoms': ['fever'], 'chief_complaint': 'Unwell', 'breastfeeding': False,
            'is_pregnant': False,
            'vitals': {
                'temperatureC': 38.5, 'heartRateBpm': 104, 'respiratoryRate': 20,
                'spo2Percent': 97, 'systolicBp': 120, 'diastolicBp': 80,
            },
            'laboratory_results': [{'name': 'Supplied test', 'value': '1', 'unit': 'mmol/L'}],
        }, context)
        self.assertEqual(set(payload), {
            'age', 'sex', 'is_pregnant', 'symptoms', 'vitals', 'labs', 'radiology',
            'medical_history', 'allergies', 'current_medications', 'previous_diagnoses', 'observations',
        })
        self.assertEqual(payload['medical_history'], ['Example condition'])
        self.assertEqual(payload['current_medications'], ['Example drug Example dose'])
        self.assertEqual(payload['radiology'], ['Example finding'])
        self.assertEqual(payload['labs'], [{'test': 'Supplied test', 'value': 1.0, 'unit': 'mmol/L'}])
        self.assertEqual(payload['is_pregnant'], False)
        self.assertEqual(payload['vitals'], {
            'temperature': 38.5, 'heart_rate': 104, 'respiratory_rate': 20,
            'oxygen_saturation': 97, 'blood_pressure': '120/80',
        })
        self.assertIn('breastfeeding: False', payload['observations'])
        historical_payload = build_analysis_payload(patient, {}, context)
        self.assertEqual(historical_payload['labs'], [
            {'test': 'Example parameter', 'value': 1, 'unit': ''},
        ])
        self.assertEqual(historical_payload['radiology'], ['Example finding'])
        for identifier in ('PAT-001', '1994-01-01', 'private-doctor', 'RX-private', 'LAB-private', 'IMG-private'):
            self.assertNotIn(identifier, str(payload))

    def test_payload_uses_chief_complaint_when_symptoms_are_empty_and_rejects_bad_lab_values(self):
        patient = Mock(age=47, gender='female')
        payload = build_analysis_payload(patient, {
            'chief_complaint': 'Headache',
            'symptoms': '',
            'is_pregnant': True,
            'laboratory_results': [{'name': 'White cell count', 'value': '12.5', 'unit': '10^9/L'}],
        }, {})
        self.assertEqual(payload['symptoms'], ['Headache'])
        self.assertEqual(payload['labs'], [{'test': 'White cell count', 'value': 12.5, 'unit': '10^9/L'}])

        qualitative_payload = build_analysis_payload(patient, {
            'chief_complaint': 'Headache',
            'laboratory_results': [{'name': 'Urine protein', 'value': 'Trace', 'unit': ''}],
        }, {})
        self.assertEqual(qualitative_payload['labs'], [
            {'test': 'Urine protein', 'value': 'Trace', 'unit': ''},
        ])
        with self.assertRaises(ValidationError):
            build_analysis_payload(patient, {
                'chief_complaint': 'Headache',
                'laboratory_results': [{'name': 'White cell count', 'value': '', 'unit': '10^9/L'}],
            }, {})

    def test_frontend_camel_case_fields_map_to_analyzer_schema(self):
        serializer = ClinicalAIConsultationRequestSerializer(data={
            'patientId': 'PAT-001',
            'isPregnant': True,
            'symptoms': ['fever'],
            'vitals': {
                'temperatureC': '38.5', 'heartRateBpm': '104', 'respiratoryRate': '20',
                'spo2Percent': '97', 'systolicBp': '120', 'diastolicBp': '80',
                'bloodGlucoseMmol': '4', 'heightCm': '170', 'weightKg': '65',
            },
            'laboratoryResults': [{
                'id': 'LAB-1', 'name': 'White cell count', 'value': '12.5',
                'unit': '10^9/L', 'referenceRange': '4-11',
            }],
            'imagingReports': [{
                'id': 'IMG-1', 'modality': 'CT Scan', 'studyName': 'Chest CT',
                'bodyPart': 'Thorax', 'findings': 'Clear', 'impression': 'No acute findings',
            }],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        payload = build_analysis_payload(Mock(age=47, gender='female'), serializer.validated_data, {})
        self.assertEqual(payload['is_pregnant'], True)
        self.assertEqual(payload['vitals'], {
            'temperature': 38.5, 'heart_rate': 104, 'respiratory_rate': 20,
            'oxygen_saturation': 97, 'blood_pressure': '120/80',
        })
        self.assertEqual(payload['labs'], [{
            'test': 'White cell count', 'value': 12.5, 'unit': '10^9/L',
        }])
        self.assertEqual(payload['radiology'], ['CT Scan: Chest CT: Thorax. Clear; No acute findings'])
        self.assertIn('height_cm: 170', payload['observations'])
        self.assertIn('weight_kg: 65', payload['observations'])
        self.assertIn('blood_glucose_mmol: 4', payload['observations'])


class ClinicalAIApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Facility 1
        self.facility1 = Facility.objects.create(
            name="Afyora Central Hospital",
            facility_type="hospital",
            registration_number="REG-F1-001",
            email="f1@afyora.com",
            phone="+254700000001",
        )

        # Facility 2
        self.facility2 = Facility.objects.create(
            name="St Jude Clinic",
            facility_type="clinic",
            registration_number="REG-F2-002",
            email="f2@afyora.com",
            phone="+254700000002",
        )

        # Doctor 1 in Facility 1
        self.doctor1 = User.objects.create_user(
            username="dr_alice",
            email="alice@afyora.com",
            password="Password123!",
            role="doctor",
            facility=self.facility1,
            is_verified=True,
        )

        # Doctor 2 in Facility 2
        self.doctor2 = User.objects.create_user(
            username="dr_bob",
            email="bob@afyora.com",
            password="Password123!",
            role="doctor",
            facility=self.facility2,
            is_verified=True,
        )

        # Patient 1 in Facility 1
        self.patient1 = Patient.objects.create(
            facility=self.facility1,
            patient_id="PAT-001",
            first_name="Jane",
            last_name="Doe",
            gender="female",
            age=32,
        )

        # Patient 2 in Facility 2
        self.patient2 = Patient.objects.create(
            facility=self.facility2,
            patient_id="PAT-002",
            first_name="John",
            last_name="Smith",
            gender="male",
            age=45,
        )

    @patch('clinical_ai.services.ai_gateway.requests.post')
    @override_settings(CLINICAL_AI_BASE_URL='https://clinical.example', CLINICAL_AI_TOKEN='test-token')
    def test_consultation_endpoint_authenticated(self, post):
        post.return_value = Mock(status_code=200, json=Mock(return_value=analysis_result()))
        self.client.force_authenticate(user=self.doctor1)
        url = reverse('clinical-ai-consultation')
        payload = {
            "patient_id": self.patient1.patient_id,
            "is_pregnant": False,
            "chief_complaint": "High grade fever and chills",
            "symptoms": "Fever, joint pain, headache, nausea",
            "vitals": {
                "temperature_c": 38.9,
                "systolic_bp": 115,
                "diastolic_bp": 75,
                "heart_rate_bpm": 95,
                "spo2_percent": 97.0,
            }
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("clinical_summary", response.data)
        self.assertIn("disclaimer", response.data)
        self.assertEqual(response.data['analysis']['supported_diagnosis'], analysis_result()['supported_diagnosis'])
        self.assertEqual(response.data['analysis']['recommended_investigations'], ['Suggested investigation'])
        self.assertEqual(response.data['recommended_investigations'][0]['test_name'], 'Suggested investigation')
        self.assertEqual(response.data['differential_diagnoses'][0]['disease'], 'Possible condition')
        self.assertEqual(response.data['confidence_level'], 'unknown')
        self.assertEqual(response.data['risk_level'], 'high')
        self.assertEqual(response.data['urgency'], 'urgent')
        self.assertTrue(response.data['referral_recommendation']['required'])
        self.assertIn('triage', response.data['analysis'])
        self.assertEqual(response.data['request_id'], response['X-Request-ID'])
        self.assertEqual(response.data['treatment_recommendations'], [])
        upstream = post.call_args.kwargs['json']
        self.assertEqual(upstream['symptoms'], ['Fever, joint pain, headache, nausea'])
        self.assertNotIn('patient_id', upstream)
        self.assertNotIn('patient', upstream)
        self.assertNotIn('clinician_id', upstream)
        self.assertEqual(upstream['is_pregnant'], False)
        self.assertEqual(upstream['vitals'], {
            'temperature': 38.9, 'heart_rate': 95, 'oxygen_saturation': 97.0,
            'blood_pressure': '115/75',
        })
        self.assertIn('labs', upstream)
        self.assertIn('radiology', upstream)
        self.assertNotIn('laboratory_results', upstream)
        self.assertNotIn('radiology_results', upstream)
        self.assertTrue(response.data['requires_human_review'])
        self.assertEqual(ClinicalAIConsultation.objects.filter(facility=self.facility1).count(), 1)
        self.assertEqual(ClinicalAIAuditEvent.objects.filter(facility=self.facility1).count(), 2)
        consultation = ClinicalAIConsultation.objects.get(facility=self.facility1)
        self.assertEqual(consultation.status, 'completed')
        self.assertEqual(consultation.recommendations.count(), 4)

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_consultation_requires_explicit_pregnancy_status(self, post):
        self.client.force_authenticate(user=self.doctor1)
        response = self.client.post(reverse('clinical-ai-consultation'), {
            'patient_id': self.patient1.patient_id,
            'symptoms': ['fever'],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('is_pregnant', response.data)
        post.assert_not_called()

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_cross_facility_patient_access_forbidden(self, post):
        """Doctor 1 (Facility 1) attempting to request AI for Patient 2 (Facility 2) must be blocked."""
        self.client.force_authenticate(user=self.doctor1)
        url = reverse('clinical-ai-consultation')
        payload = {
            "patient_id": self.patient2.patient_id,
            "is_pregnant": False,
            "chief_complaint": "Headache",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        post.assert_not_called()

    @override_settings(CLINICAL_AI_BASE_URL='https://clinical.example', CLINICAL_AI_TOKEN='test-token')
    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_failed_analysis_is_recorded_and_returned_as_error(self, post):
        self.client.force_authenticate(user=self.doctor1)
        for upstream in (429, 502, 503, 504):
            with self.subTest(upstream=upstream):
                post.return_value = Mock(status_code=upstream)
                response = self.client.post(reverse('clinical-ai-consultation'), {
                    'patientId': 'PAT-001', 'isPregnant': False, 'symptoms': ['fever'],
                }, format='json')
                self.assertEqual(response.status_code, upstream)
                self.assertEqual(response.data['request_id'], response['X-Request-ID'])
                self.assertNotIn('clinical_summary', response.data)
                consultation = ClinicalAIConsultation.objects.latest('id')
                self.assertEqual(consultation.status, 'failed')
                self.assertIsNone(consultation.raw_response)
                self.assertEqual(consultation.recommendations.count(), 0)
                self.assertEqual(post.call_args.kwargs['json']['symptoms'], ['fever'])

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_invalid_inputs_do_not_call_standalone_service(self, post):
        self.client.force_authenticate(user=self.doctor1)
        for invalid in ({'symptoms': [42]}, {'vitals': {'temperature': []}}, {'laboratoryResults': [42]}, {'imagingReports': [False]}):
            response = self.client.post(reverse('clinical-ai-consultation'), {'patientId': 'PAT-001', **invalid}, format='json')
            self.assertEqual(response.status_code, 400)
        post.assert_not_called()

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_unauthenticated_requests_do_not_call_standalone_service(self, post):
        response = self.client.post(reverse('clinical-ai-consultation'), {'patientId': 'PAT-001'}, format='json')
        self.assertIn(response.status_code, (401, 403))
        post.assert_not_called()

    @patch('clinical_ai.services.ai_gateway.requests.post')
    def test_chat_is_retired_without_an_upstream_call(self, post):
        self.client.force_authenticate(user=self.doctor1)
        response = self.client.post(reverse('clinical-ai-chat'), {'message': 'Example'}, format='json')
        self.assertEqual(response.status_code, 410)
        post.assert_not_called()

    def test_patient_history_endpoint(self):
        self.client.force_authenticate(user=self.doctor1)
        url = reverse('clinical-ai-patient-history', kwargs={'patient_id': self.patient1.patient_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("demographics", response.data)
        self.assertIn("allergies", response.data)

    def test_feedback_endpoint(self):
        self.client.force_authenticate(user=self.doctor1)
        consultation = ClinicalAIConsultation.objects.create(
            facility=self.facility1,
            patient=self.patient1,
            requested_by=self.doctor1,
            status='completed',
            chief_complaint='Fever',
        )

        url = reverse('clinical-ai-feedback')
        payload = {
            "consultation_id": consultation.id,
            "action": "accepted",
            "rating": 5,
            "feedback": "Accurate differential diagnosis.",
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClinicalAIFeedback.objects.filter(facility=self.facility1).count(), 1)

    def test_prescription_approve_endpoint(self):
        self.client.force_authenticate(user=self.doctor1)
        url = reverse('clinical-ai-prescription-approve')
        payload = {
            "patient_id": self.patient1.patient_id,
            "drugs": [
                {"name": "Artemether + Lumefantrine", "dosage": "80/480mg BID", "duration": "3 days"}
            ],
            "is_modified": False,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("prescription_id", response.data)
        self.assertEqual(response.data["signed_by"], self.doctor1.username)
