from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.core.cache import cache
from django.urls import reverse
import requests

from interoperability.services.kmhfr import KMHFRService


class KMHFRServiceTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch('requests.get')
    def test_search_facilities_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'count': 1,
            'results': [{'id': '123', 'name': 'Kenyatta National Hospital'}]
        }
        mock_get.return_value = mock_response

        result = KMHFRService.search_facilities(search_query='Kenyatta', page=1, page_size=10)

        self.assertFalse(result['error'])
        self.assertEqual(result['status_code'], 200)
        self.assertEqual(result['data']['count'], 1)
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_search_facilities_caching(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'results': []}
        mock_get.return_value = mock_response

        # First call -> hits API
        res1 = KMHFRService.search_facilities(search_query='Nairobi', page=1)
        # Second call -> hits cache
        res2 = KMHFRService.search_facilities(search_query='Nairobi', page=1)

        self.assertEqual(res1, res2)
        # requests.get should only have been called once due to caching
        self.assertEqual(mock_get.call_count, 1)

    @patch('requests.get')
    def test_search_facilities_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        result = KMHFRService.search_facilities(search_query='Mombasa')

        self.assertFalse(result['error'])
        self.assertEqual(result['status_code'], 200)
        self.assertTrue(result['fallback'])
        self.assertGreaterEqual(result['data']['count'], 1)

    @patch('requests.get')
    def test_search_facilities_upstream_500_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        result = KMHFRService.search_facilities(search_query='Nakuru')

        self.assertFalse(result['error'])
        self.assertEqual(result['status_code'], 200)
        self.assertTrue(result['fallback'])
        self.assertGreaterEqual(result['data']['count'], 1)


class FacilitySearchViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()

    @patch.object(KMHFRService, 'search_facilities')
    def test_facility_search_view_success(self, mock_search):
        mock_search.return_value = {
            'error': False,
            'status_code': 200,
            'data': {'results': [{'name': 'Moi Teaching and Referral Hospital'}]}
        }

        response = self.client.get('/api/facilities/search/?q=Moi&page=1&page_size=10')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['error'])
        self.assertEqual(data['data']['results'][0]['name'], 'Moi Teaching and Referral Hospital')
        mock_search.assert_called_once_with(
            search_query='Moi',
            county=None,
            facility_type=None,
            page=1,
            page_size=10
        )

    def test_facility_search_view_invalid_page(self):
        response = self.client.get('/api/facilities/search/?page=invalid')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data['error'])
        self.assertIn("Invalid 'page' parameter", data['message'])

    def test_facility_search_view_invalid_page_size(self):
        response = self.client.get('/api/facilities/search/?page_size=500')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertTrue(data['error'])
        self.assertIn("Invalid 'page_size' parameter", data['message'])
