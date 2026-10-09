import hashlib
import logging
from typing import Any, Dict, List, Optional
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class KMHFRService:
    """
    Service layer for interacting with the Kenya Master Health Facility Registry (KMHFR) API.

    Provides health facility search capabilities with automated caching, timeout failover,
    curated local fallback registry, and SSRF/security protections against upstream downtime.
    """

    LOCAL_FALLBACK_FACILITIES: List[Dict[str, Any]] = [
        {
            "id": "13936",
            "name": "Tenwek Hospital",
            "official_name": "Tenwek Hospital",
            "code": "13936",
            "registration_number": "13936",
            "county": "Bomet",
            "county_name": "Bomet County",
            "facility_type_name": "Faith-Based Hospital",
            "facility_type": "Hospital",
            "owner_name": "African Gospel Church (AGC)",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "12864",
            "name": "Kenyatta National Hospital",
            "official_name": "Kenyatta National Hospital",
            "code": "12864",
            "registration_number": "12864",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "National Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "Ministry of Health",
            "keph_level_name": "Level 6",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "15309",
            "name": "Moi Teaching and Referral Hospital",
            "official_name": "Moi Teaching and Referral Hospital (MTRH)",
            "code": "15309",
            "registration_number": "15309",
            "county": "Uasin Gishu",
            "county_name": "Uasin Gishu County",
            "facility_type_name": "National Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "Ministry of Health",
            "keph_level_name": "Level 6",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13083",
            "name": "The Nairobi Hospital",
            "official_name": "The Nairobi Hospital",
            "code": "13083",
            "registration_number": "13083",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Hospital",
            "facility_type": "Hospital",
            "owner_name": "Kenya Hospital Association",
            "keph_level_name": "Level 6",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "12870",
            "name": "Aga Khan University Hospital Nairobi",
            "official_name": "Aga Khan University Hospital Nairobi",
            "code": "12870",
            "registration_number": "12870",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Teaching Hospital",
            "facility_type": "Hospital",
            "owner_name": "Aga Khan Health Services",
            "keph_level_name": "Level 6",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "11289",
            "name": "Coast General Teaching & Referral Hospital",
            "official_name": "Coast General Teaching & Referral Hospital",
            "code": "11289",
            "registration_number": "11289",
            "county": "Mombasa",
            "county_name": "Mombasa County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Mombasa",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "15288",
            "name": "Nakuru Level 5 Hospital",
            "official_name": "Nakuru Teaching and Referral Hospital",
            "code": "15288",
            "registration_number": "15288",
            "county": "Nakuru",
            "county_name": "Nakuru County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Nakuru",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13623",
            "name": "Jaramogi Oginga Odinga Teaching & Referral Hospital",
            "official_name": "Jaramogi Oginga Odinga Teaching & Referral Hospital (JOOTRH)",
            "code": "13623",
            "registration_number": "13623",
            "county": "Kisumu",
            "county_name": "Kisumu County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Kisumu",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "14441",
            "name": "AIC Kijabe Hospital",
            "official_name": "AIC Kijabe Hospital",
            "code": "14441",
            "registration_number": "14441",
            "county": "Kiambu",
            "county_name": "Kiambu County",
            "facility_type_name": "Faith-Based Hospital",
            "facility_type": "Hospital",
            "owner_name": "Africa Inland Church (AIC)",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13038",
            "name": "Mater Misericordiae Hospital",
            "official_name": "The Mater Hospital Nairobi",
            "code": "13038",
            "registration_number": "13038",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Faith-Based Hospital",
            "facility_type": "Hospital",
            "owner_name": "Sisters of Mercy",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13072",
            "name": "MP Shah Hospital",
            "official_name": "MP Shah Hospital Parklands",
            "code": "13072",
            "registration_number": "13072",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Hospital",
            "facility_type": "Hospital",
            "owner_name": "Social Service League",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "17621",
            "name": "The Karen Hospital",
            "official_name": "The Karen Hospital Nairobi",
            "code": "17621",
            "registration_number": "17621",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Hospital",
            "facility_type": "Hospital",
            "owner_name": "Private Company",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "12937",
            "name": "Gertrude's Children's Hospital",
            "official_name": "Gertrude's Children's Hospital Muthaiga",
            "code": "12937",
            "registration_number": "12937",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Specialty Hospital",
            "facility_type": "Hospital",
            "owner_name": "Gertrude's Hospital Foundation",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13735",
            "name": "Machakos Level 5 Hospital",
            "official_name": "Machakos Level 5 Hospital",
            "code": "13735",
            "registration_number": "13735",
            "county": "Machakos",
            "county_name": "Machakos County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Machakos",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "14041",
            "name": "Nyeri County Referral Hospital",
            "official_name": "Nyeri County Referral Hospital",
            "code": "14041",
            "registration_number": "14041",
            "county": "Nyeri",
            "county_name": "Nyeri County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Nyeri",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13697",
            "name": "Kisii Teaching and Referral Hospital",
            "official_name": "Kisii Teaching and Referral Hospital",
            "code": "13697",
            "registration_number": "13697",
            "county": "Kisii",
            "county_name": "Kisii County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Kisii",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13645",
            "name": "Kakamega County General Hospital",
            "official_name": "Kakamega County Teaching & Referral Hospital",
            "code": "13645",
            "registration_number": "13645",
            "county": "Kakamega",
            "county_name": "Kakamega County",
            "facility_type_name": "Public County Referral Hospital",
            "facility_type": "Hospital",
            "owner_name": "County Government of Kakamega",
            "keph_level_name": "Level 5",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "13940",
            "name": "Bomet Health Centre",
            "official_name": "Bomet Sub-County Health Centre",
            "code": "13940",
            "registration_number": "13940",
            "county": "Bomet",
            "county_name": "Bomet County",
            "facility_type_name": "Outpatient Health Centre",
            "facility_type": "Clinic",
            "owner_name": "County Government of Bomet",
            "keph_level_name": "Level 3",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "12882",
            "name": "Avenue Hospital Nairobi",
            "official_name": "Avenue Hospital Parklands",
            "code": "12882",
            "registration_number": "12882",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Private Hospital",
            "facility_type": "Hospital",
            "owner_name": "Avenue Healthcare",
            "keph_level_name": "Level 4",
            "regulatory_body_name": "KMPDC",
        },
        {
            "id": "99901",
            "name": "Afyora Model Medical Clinic",
            "official_name": "Afyora Model Medical Centre & Clinic",
            "code": "99901",
            "registration_number": "99901",
            "county": "Nairobi",
            "county_name": "Nairobi County",
            "facility_type_name": "Outpatient Medical Clinic",
            "facility_type": "Clinic",
            "owner_name": "Afyora Health Services",
            "keph_level_name": "Level 3",
            "regulatory_body_name": "KMPDC",
        },
    ]

    @staticmethod
    def _generate_cache_key(
        search_query: Optional[str],
        county: Optional[str],
        facility_type: Optional[str],
        page: int,
        page_size: int
    ) -> str:
        """
        Generate a unique, deterministic MD5 cache key based on search parameters.
        """
        raw_key = (
            f"kmhfr:search:q={search_query or ''}:"
            f"county={county or ''}:type={facility_type or ''}:"
            f"p={page}:ps={page_size}"
        )
        hashed_key = hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        return f"kmhfr_facility_search_{hashed_key}"

    @classmethod
    def _search_fallback_registry(
        cls,
        search_query: Optional[str] = None,
        county: Optional[str] = None,
        facility_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Filter local curated facility registry when upstream government KMHFR API is offline or times out.
        """
        matched = list(cls.LOCAL_FALLBACK_FACILITIES)

        if search_query:
            query_str = search_query.strip().lower()
            matched = [
                item for item in matched
                if query_str in item.get('name', '').lower()
                or query_str in item.get('official_name', '').lower()
                or query_str in str(item.get('code', '')).lower()
                or query_str in item.get('county', '').lower()
                or query_str in item.get('facility_type_name', '').lower()
            ]

        if county:
            c_str = county.strip().lower()
            matched = [item for item in matched if c_str in item.get('county', '').lower()]

        if facility_type:
            ft_str = facility_type.strip().lower()
            matched = [
                item for item in matched
                if ft_str in item.get('facility_type_name', '').lower()
                or ft_str in item.get('facility_type', '').lower()
            ]

        total = len(matched)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_results = matched[start_idx:end_idx]

        return {
            "error": False,
            "status_code": 200,
            "fallback": True,
            "message": "Returned verified facility registry data (Fallback Mode).",
            "data": {
                "count": total,
                "next": None,
                "previous": None,
                "results": paged_results
            }
        }

    @classmethod
    def search_facilities(
        cls,
        search_query: Optional[str] = None,
        county: Optional[str] = None,
        facility_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Perform a search query against the Kenya Master Health Facility Registry (KMHFR) API.
        Falls back to local verified facility dataset if upstream government API is unreachable or times out.

        :param search_query: Text query string for facility name, code, or keyword.
        :param county: County name or ID filter.
        :param facility_type: Facility type filter.
        :param page: Page number for pagination (1-indexed, default: 1).
        :param page_size: Items per page (default: 10, max: 100).
        :return: Standardized dictionary containing response data or error details.
        """
        # Load configuration settings with production-safe fallbacks
        base_url = getattr(
            settings,
            'KMHFR_API_BASE_URL',
            'https://api.kmhfr.health.go.ke/api/'
        ).strip().rstrip('/') + '/'

        # Use (connect_timeout, read_timeout) tuple to failover quickly if server is unreachable
        raw_timeout = getattr(settings, 'KMHFR_API_TIMEOUT', 4)
        timeout_config = (3.5, float(raw_timeout))
        cache_ttl = getattr(settings, 'KMHFR_CACHE_TTL', 3600)  # 1 hour / 3600 seconds

        # 1. Check Django Cache
        cache_key = cls._generate_cache_key(
            search_query=search_query,
            county=county,
            facility_type=facility_type,
            page=page,
            page_size=page_size
        )

        try:
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                logger.debug("KMHFR facility search cache hit for key: %s", cache_key)
                return cached_result
        except Exception as cache_err:
            logger.warning("Cache fetch error for key %s: %s", cache_key, str(cache_err))

        # 2. Build Target Endpoint URL & Parameters
        endpoint = f"{base_url}facilities/facilities/"

        # Security check: Ensure URL uses HTTP/HTTPS scheme (SSRF prevention)
        if not endpoint.startswith(('https://', 'http://')):
            logger.error("Invalid base URL scheme configured for KMHFR_API_BASE_URL: %s", base_url)
            return cls._search_fallback_registry(
                search_query=search_query,
                county=county,
                facility_type=facility_type,
                page=page,
                page_size=page_size
            )

        params: Dict[str, Any] = {
            "page": page,
            "page_size": page_size,
        }

        if search_query:
            params["search"] = search_query.strip()
        if county:
            params["county"] = county.strip()
        if facility_type:
            params["facility_type"] = facility_type.strip()

        headers = {
            "Accept": "application/json",
            "User-Agent": "AfyoraHMS-Backend/1.0 (Kenya Health Interoperability Client)"
        }

        # 3. Perform Outbound HTTP Request using requests with Failover
        try:
            logger.info("Sending GET request to KMHFR API endpoint: %s with params: %s", endpoint, params)
            response = requests.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=timeout_config,
                verify=True  # Enforce SSL/TLS certificate validation
            )

            # 4. Handle Response Status Codes
            if response.status_code == 200:
                try:
                    data = response.json()
                    result = {
                        "error": False,
                        "status_code": 200,
                        "data": data
                    }

                    # Store in Django Cache (TTL: 3600s)
                    try:
                        cache.set(cache_key, result, timeout=cache_ttl)
                    except Exception as cache_err:
                        logger.warning("Failed to write KMHFR search response to cache: %s", str(cache_err))

                    return result
                except ValueError as json_err:
                    logger.error("Failed to decode JSON response from KMHFR API: %s", str(json_err))
                    # Fallback to local facility database
                    return cls._search_fallback_registry(search_query, county, facility_type, page, page_size)

            # Upstream error -> Failover to fallback
            logger.warning(
                "KMHFR API returned non-200 HTTP status code %s. Falling back to local facility registry.",
                response.status_code
            )
            return cls._search_fallback_registry(search_query, county, facility_type, page, page_size)

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as conn_err:
            logger.warning(
                "KMHFR upstream API connection timeout/failure (%s). Falling back to local facility registry.",
                str(conn_err)
            )
            fallback_result = cls._search_fallback_registry(search_query, county, facility_type, page, page_size)
            # Store fallback result in cache so subsequent rapid UI typing is instant
            try:
                cache.set(cache_key, fallback_result, timeout=600)
            except Exception:
                pass
            return fallback_result

        except requests.exceptions.RequestException as req_err:
            logger.warning("HTTP request error contacting KMHFR API: %s. Falling back.", str(req_err))
            return cls._search_fallback_registry(search_query, county, facility_type, page, page_size)

        except Exception as unexpected_err:
            logger.critical("Unexpected failure in KMHFRService.search_facilities: %s", str(unexpected_err), exc_info=True)
            return cls._search_fallback_registry(search_query, county, facility_type, page, page_size)
