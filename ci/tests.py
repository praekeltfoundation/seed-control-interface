import responses
import os

from tempfile import NamedTemporaryFile

from openpyxl import load_workbook

from django.test import TestCase, Client, override_settings
from django.core.management import call_command
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
            'details': {
                'default_addr_type': 'msisdn',
                'addresses': {
                    'msisdn': {
                        '1234567890': {},
                    }
                }
            }
        }), {'1234567890': {}})

    def test_get_identy_addresses_bad(self):
        self.assertEqual(get_identity_addresses({}), {})
        self.assertEqual(get_identity_addresses({
            'details': {
                'default_addr_type': 'msisdn'
            }
        }), {})
        self.assertEqual(get_identity_addresses({
            'details': {
                'default_addr_type': 'foo',
                'addresses': {
                    'msisdn': {
                        '1234567890': {},
                    }
                }
            }
        }), {})


@override_settings(
    HUB_URL='http://hub/',
    HUB_TOKEN='hubtoken',
    IDENTITY_STORE_URL='http://idstore/',
    IDENTITY_STORE_TOKEN='idstoretoken')
class GenerateReportTest(TestCase):

    def assertSheetRow(self, file_name, sheet_name, row_number, expected):
        wb = load_workbook(file_name)
        sheet = wb[sheet_name]
        rows = list(sheet.rows)
        self.assertEqual(
            [cell.value for cell in rows[row_number]],
            expected)

    def mk_tempfile(self):
        tmp_file = NamedTemporaryFile(suffix='.xlsx')
        self.addCleanup(tmp_file.close)
        return tmp_file

    @responses.activate
    def test_generate_report(self):

        # Registrations
        responses.add(
            responses.GET,
            'http://hub/registrations/',
            json={
                'count': 1,
                'results': [{
                    'created_at': 'created-at',
                    'data': {
                        'operator_id': 'operator_id',
                        'gravida': 'gravida',
                        'msg_type': 'msg_type',
                        'last_period_date': 'last_period_date',
                        'language': 'language',
                        'msg_receiver': 'msg_receiver',
                        'voice_days': 'voice_days',
                        'voice_times': 'voice_times',
                        'preg_week': 'preg_week',
                        'reg_type': 'reg_type',
                    }
                }]
            },
            status=200,
            content_type='application/json')

        # Identities
        responses.add(
            responses.GET,
            'http://idstore/identities/operator_id/',
            json={
                'identity': 'operator_id',
                'details': {
                    'personnel_code': 'personnel_code',
                    'facility_name': 'facility_name',
                    'role': 'role',
                    'state': 'state',
                }
            },
            status=200,
            content_type='application/json')

        tmp_file = self.mk_tempfile()

        call_command(
            'generate_reports',
            '--start', '2016-01-01', '--end', '2016-02-01',
            '--output-file', tmp_file.name)

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'Registrations by date', 0,
            [
                'Created',
                'gravida',
                'msg_type',
                'last_period_date',
                'language',
                'msg_receiver',
                'voice_days',
                'Voice_times',
                'preg_week',
                'reg_type',
                'Personnel_code',
                'Facility',
                'Cadre',
                'State',
            ])

        # Assert 1 row is written
        self.assertSheetRow(
            tmp_file.name, 'Registrations by date', 1,
            [
                'created-at',
                'gravida',
                'msg_type',
                'last_period_date',
                'language',
                'msg_receiver',
                'voice_days',
                'voice_times',
                'preg_week',
                'reg_type',
                'personnel_code',
                'facility_name',
                'role',
                'state',
            ])
