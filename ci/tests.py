from django.test import TestCase, Client
from .views import get_identity_addresses


class ViewTests(TestCase):

    def setUp(self):
        self.client = Client()

    def login(self):
        self.client.login(username='testuser', password='testpass')

    def test_redirect_to_login(self):
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please login to see this page")

    def test_get_identy_addresses_good(self):
        self.assertEqual(get_identity_addresses({
            'default_addr_type': 'msisdn',
            'addresses': {
                'msisdn': {
                    '1234567890': {},
                }
            }
        }), {'1234567890': {}})

    def test_get_identy_addresses_bad(self):
        self.assertEqual(get_identity_addresses({}), {})
        self.assertEqual(get_identity_addresses({
            'default_addr_type': 'msisdn'
        }), {})
        self.assertEqual(get_identity_addresses({
            'default_addr_type': 'foo',
            'addresses': {
                'msisdn': {
                    '1234567890': {},
                }
            }
        }), {})
