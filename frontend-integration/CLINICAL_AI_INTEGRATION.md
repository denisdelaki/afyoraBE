# Standalone Clinical AI Gateway

Django no longer hosts an inference engine. The request flow is:

Frontend -> authenticated Django consultation endpoint -> standalone Clinical AI
`POST /api/clinical-ai/analyze/` -> validated response -> Django storage and frontend.

## Backend Configuration

Register an application on the standalone service's `/integrations/` dashboard and
store its one-time bearer token in Django's backend environment:

```dotenv
CLINICAL_AI_BASE_URL=https://your-clinical-ai-service.example
CLINICAL_AI_TOKEN=your-registered-application-token
CLINICAL_AI_TIMEOUT=45
```

Local development may use `http://127.0.0.1:8001`. Non-loopback URLs must use HTTPS.
The base URL is the standalone application's origin, not its analyze endpoint.
Configure these values in Render before deployment. The local token is intentionally
blank until an operator supplies the actual registered token. Missing configuration
returns 503. Never expose the integration token to the frontend or commit it.
The old shared-secret JWT and `FASTAPI_*` settings are no longer used.

## Frontend Request

Keep using the existing Django URL and your normal user authentication:

```http
POST /api/clinical-ai/consultation/
Authorization: Bearer <Django-user-access-token>
Content-Type: application/json
```

```json
{
  "patientId": "PAT-001",
  "isPregnant": false,
  "chiefComplaint": "Fever and headache",
  "symptoms": ["fever", "headache"],
  "vitals": { "temperature": 38.5 },
  "laboratoryResults": [],
  "imagingReports": []
}
```

Snake-case names remain supported. `isPregnant` is required as an explicit boolean;
the backend does not infer a negative pregnancy status when it is omitted. The
legacy `pregnancyStatus` accepts `yes`/`pregnant` or `no`/`not pregnant`. `symptoms`
accepts the existing string format or an array of strings. Vital values must be
numbers, strings, or null; lab and
imaging results must be strings or objects. Lab results must be objects with a test name and a
numeric value (numeric strings are normalized); imaging results may be strings or
objects. The patient's active facility must
match the authenticated clinician's facility. Django retrieves authorized history,
allergies, medications, previous diagnoses, and recent investigation results.
Supplied nonempty lab/imaging lists take precedence over historical lists.
Patient, clinician, facility, prescription, lab, and imaging identifiers and date
of birth are excluded from the outbound payload. Relevant result fields are
allowlisted. Free-text clinical fields can still contain identifying information;
use the minimum approved clinical information and appropriate consent controls.

## Analyzer Response

The standalone `POST /api/clinical-ai/analyze/` endpoint must return this exact
shape. Extra or missing fields are rejected; `requires_human_review` must be true.
The analyzer response does not include a confidence score.

```json
{
  "supported_diagnosis": "Provisional assessment; clinician review required.",
  "possible_disease": ["Possible condition"],
  "drugs_admissible": [],
  "further_labs_to_be_done": ["Suggested investigation"],
  "triage": {
    "level": "urgent",
    "urgent_care_recommended": true,
    "reasons": ["Oxygen saturation meets an urgent screening threshold."],
    "unassessed_vitals": ["respiratory_rate"],
    "recommendation": "Urgent in-person clinical assessment is recommended now.",
    "requires_human_review": true,
    "rule_set": "adult-vital-screening-v1"
  }
}
```

## Frontend Response

Success returns HTTP 200. Existing keys such as `consultation_id`,
`clinical_summary`, `red_flags`, `emergency`, `urgency`, `differential_diagnoses`,
`recommended_investigations`, `medication_safety`, `confidence_level`, and
`disclaimer` remain available. Differentials retain `disease` and
`supporting_findings`; investigation objects retain `test_name`, `indication`,
and `urgency`. No codes, evidence citations, or model versions are invented.

New clients should use `analysis`, which contains the native analyzer fields plus
the mapped compatibility fields. `supported_diagnosis` maps to `clinical_summary`,
`possible_disease` maps to `possible_conditions`, `further_labs_to_be_done` maps to
`recommended_investigations`, and `triage` supplies risk, referral, and review fields.
No confidence score is fabricated: `analysis.confidence` is null and
`confidence_level` is `unknown`. Native fields are also exposed at the top level;
`recommended_investigations` retains the legacy object format there.
`request_id` is returned in the body and `X-Request-ID` header for correlation.

`requires_human_review` must be true. Medication considerations are advisory text,
not prescriptions: `treatment_recommendations` stays empty. A clinician must
independently review and author any prescription. The existing explicit approval
endpoint remains available, along with local feedback, patient history, and
consultation detail endpoints. Feedback is stored locally, not sent to an
undocumented standalone feedback endpoint. Consultation details retain the
packaged response in `raw_response`.

`POST /api/clinical-ai/chat/` is retired and returns 410 `chat_not_supported`.
Disable the old chat UI; the provided standalone contract supports analysis only.

## Errors and Operations

Failures are never returned as successful assessments. Errors contain
`error.code`, `error.message`, and `request_id`. Upstream HTTP failures also
include `error.upstream_status` and, when recognized, an allowlisted
`error.upstream_code`. Provider failures (`ai_provider_error`), invalid model
output (`ai_invalid_response`), and internal standalone failures
(`ai_analysis_failed`) are reported separately. Unknown codes and raw error
messages are never forwarded. An upstream 502 means the standalone service
returned an error, not that Django's response validator rejected a successful
assessment. Use the request ID to inspect that service's provider diagnostics.
Failed consultations are marked
failed and have no recommendations or raw model output.

| Status  | Meaning                                                                               |
| ------- | ------------------------------------------------------------------------------------- |
| 400     | Invalid frontend input or an upstream request rejection                               |
| 401/403 | Django user authentication or authorization failure                                   |
| 404     | Patient not found in the clinician's facility                                         |
| 410     | Retired chat endpoint                                                                 |
| 429     | Standalone provider rate limit                                                        |
| 502     | Unreachable service, invalid response, or other upstream failure                      |
| 503     | Missing backend configuration, rejected integration token, or provider not configured |
| 504     | Upstream timeout                                                                      |

The gateway validates the response fields and bounds before persisting anything.
It does not follow redirects or automatically retry requests. Upstream error
bodies and credentials are not logged or forwarded. Preserve `request_id` for
support without putting patient information in it. Set frontend/proxy timeouts
above the backend's configured provider timeout, allowing additional processing
time, and never render a non-200 response as an assessment.

The standalone application's no-persistence policy does not remove Django's
existing authorized consultation snapshots, results, recommendations, feedback,
or audit records. Apply the HMS's patient-data retention and access policies.

## Verification

Run the mocked integration suite without the deployment database configuration:

```sh
DATABASE_URL='' SUPABASE_DATABASE_URL='' python manage.py test clinical_ai.tests --noinput
```

These tests do not call the provider or spend quota. A live smoke test requires
the real standalone URL and registered token; use synthetic or approved
de-identified data only.
