import requests
from django.conf import settings


class KnhtsServiceError(Exception):
    pass


def _headers(api_key=None, auth_scheme=None, api_key_header=None):
    """Build HTTP headers for a FHIR request."""
    headers = {'Accept': 'application/fhir+json, application/json'}
    key = api_key if api_key is not None else settings.KNHTS_API_KEY
    if key:
        scheme = auth_scheme or settings.KNHTS_AUTH_SCHEME
        header = api_key_header or settings.KNHTS_API_KEY_HEADER
        if scheme.lower() == 'api-key':
            headers[header] = key
        else:
            headers['Authorization'] = f'{scheme} {key}'
    return headers


def _request(path, params, base_url=None, api_key=None, timeout=None):
    """
    Execute a GET request against a FHIR server.

    Parameters
    ----------
    path     : FHIR path relative to base_url (e.g. 'ValueSet/$expand')
    params   : dict of query parameters
    base_url : override the primary KNHTS_BASE_URL (used for fallback server)
    api_key  : override KNHTS_API_KEY (pass '' for no-auth public servers)
    timeout  : override KNHTS_TIMEOUT
    """
    resolved_base = (base_url or settings.KNHTS_BASE_URL or '').rstrip('/')
    if not resolved_base:
        raise KnhtsServiceError('KNHTS_BASE_URL is not configured.')

    url = f"{resolved_base}/{path.lstrip('/')}"
    try:
        response = requests.get(
            url,
            params=params,
            headers=_headers(api_key=api_key),
            timeout=timeout if timeout is not None else settings.KNHTS_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise KnhtsServiceError('The KNHTS terminology service is unavailable.') from exc


def _concept(system, code, display):
    display = display or code
    return {
        'coding': [{'system': system or 'KNHTS', 'code': code, 'display': display}],
        'text': display,
        'display': display,
        'system': system or 'KNHTS',
        'code': code,
    }


def _parameter_value(parameters, name):
    for parameter in parameters:
        if parameter.get('name') != name:
            continue
        for key, value in parameter.items():
            if key.startswith('value'):
                return value
    return ''


def _parse_concepts(payload):
    """Extract concept list from a FHIR ValueSet $expand response."""
    contains = payload.get('expansion', {}).get('contains', [])
    if not contains:
        contains = payload.get('data') or payload.get('results') or []

    concepts = []
    for item in contains:
        code = item.get('code') or item.get('conceptCode')
        coding = item.get('coding') or [{}]
        if code:
            concepts.append(
                _concept(
                    item.get('system') or coding[0].get('system'),
                    code,
                    item.get('display') or item.get('text') or item.get('name'),
                )
            )
    return concepts


# ---------------------------------------------------------------------------
# Primary helpers (use settings.KNHTS_BASE_URL)
# ---------------------------------------------------------------------------

def search_concepts(search):
    payload = _request(settings.KNHTS_SEARCH_PATH, {'filter': search, 'count': 20})
    return _parse_concepts(payload)


def lookup_concept(system, code):
    payload = _request(settings.KNHTS_LOOKUP_PATH, {'system': system, 'code': code})
    if payload.get('resourceType') == 'Parameters':
        parameters = payload.get('parameter', [])
        resolved_code = _parameter_value(parameters, 'code') or code
        display = _parameter_value(parameters, 'display') or resolved_code
        return _concept(system, resolved_code, display)

    item = payload.get('data', payload)
    if isinstance(item, list):
        item = item[0] if item else None
    if not item:
        return None
    return _concept(
        item.get('system') or system,
        item.get('code') or item.get('conceptCode') or code,
        item.get('display') or item.get('text') or item.get('name'),
    )


# ---------------------------------------------------------------------------
# Generic helpers — call any FHIR base URL (used for fallback servers)
# ---------------------------------------------------------------------------

def search_from_url(search, base_url, api_key='', timeout=None, valueset_url='http://hl7.org/fhir/ValueSet/condition-code'):
    """
    Search for concepts on *any* FHIR server (used for fallback public servers).
    Uses the same ValueSet/$expand path as the primary server.
    """
    params = {'filter': search, 'count': 20}
    if valueset_url:
        params['url'] = valueset_url

    try:
        payload = _request(
            settings.KNHTS_SEARCH_PATH,
            params,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        concepts = _parse_concepts(payload)
        if concepts:
            return concepts
    except KnhtsServiceError:
        pass

    # Try without 'url' parameter if it failed or returned no concepts
    if 'url' in params:
        del params['url']
        payload = _request(
            settings.KNHTS_SEARCH_PATH,
            params,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        return _parse_concepts(payload)

    return []


def lookup_from_url(system, code, base_url, api_key='', timeout=None):
    """
    Look up a single concept on *any* FHIR server (used for fallback public servers).
    """
    fhir_system = system
    if not fhir_system or not fhir_system.startswith('http'):
        fhir_system = 'http://snomed.info/sct'

    payload = _request(
        settings.KNHTS_LOOKUP_PATH,
        {'system': fhir_system, 'code': code},
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    if payload.get('resourceType') == 'Parameters':
        parameters = payload.get('parameter', [])
        resolved_code = _parameter_value(parameters, 'code') or code
        display = _parameter_value(parameters, 'display') or resolved_code
        return _concept(fhir_system, resolved_code, display)

    item = payload.get('data', payload)
    if isinstance(item, list):
        item = item[0] if item else None
    if not item:
        return None
    return _concept(
        item.get('system') or fhir_system,
        item.get('code') or item.get('conceptCode') or code,
        item.get('display') or item.get('text') or item.get('name'),
    )
