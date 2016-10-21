import responses

from tempfile import NamedTemporaryFile

from openpyxl import load_workbook

from django.test import TestCase, Client, override_settings
from django.core import mail
from django.core.management import call_command
from ci.management.commands.generate_reports import parse_cursor_params
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
    HUB_URL='http://hub.example.com/',
    HUB_TOKEN='hubtoken',
    IDENTITY_STORE_URL='http://idstore.example.com/',
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

    def test_parse_cursor_params(self):
        cursor = ("https://example"
                  "?created_after=2010-01-01T00%3A00%3A00%2B00%3A00"
                  "&created_before=2016-10-17T00%3A00%3A00%2B00%3A00"
                  "&limit=1000&offset=1000")
        params = parse_cursor_params(cursor)
        self.assertEqual(params['created_after'], '2010-01-01T00:00:00+00:00')
        self.assertEqual(params['created_before'], '2016-10-17T00:00:00+00:00')
        self.assertEqual(params['limit'], '1000')
        self.assertEqual(params['offset'], '1000')

    @responses.activate
    def test_generate_report(self):

        # Registrations, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        responses.add(
            responses.GET,
            ("http://hub.example.com/registrations/?"
             "created_before=2016-02-01T00%3A00%3A00%2B00%3A00"
             "&created_after=2016-01-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 1,
                'next': 'http://hub.example.com/registrations/?foo=bar',
                'results': [],
            },
            status=200,
            content_type='application/json')

        # Registrations, second page, this one has the results
        responses.add(
            responses.GET,
            'http://hub.example.com/registrations/?foo=bar',
            match_querystring=True,
            json={
                'count': 1,
                'next': None,
                'results': [{
                    'created_at': 'created-at',
                    'data': {
                        'operator_id': 'operator_id',
                        'receiver_id': 'receiver_id',
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
            'http://idstore.example.com/identities/operator_id/',
            json={
                'identity': 'operator_id',
                'details': {
                    'personnel_code': 'personnel_code',
                    'facility_name': 'facility_name',
                    'default_addr_type': 'msisdn',
                    'role': 'role',
                    'state': 'state',
                    'addresses': {
                        'msisdn': {
                            '+2340000000000': {}
                        }
                    }
                }
            },
            status=200,
            content_type='application/json')

        # Identities
        responses.add(
            responses.GET,
            'http://idstore.example.com/identities/receiver_id/',
            json={
                'identity': 'receiver_id',
                'details': {
                    'personnel_code': 'personnel_code',
                    'facility_name': 'facility_name',
                    'default_addr_type': 'msisdn',
                    'role': 'role',
                    'state': 'state',
                    'addresses': {
                        'msisdn': {
                            '+2341111111111': {}
                        }
                    }
                }
            },
            status=200,
            content_type='application/json')

        tmp_file = self.mk_tempfile()

        call_command(
            'generate_reports',
            '--start', '2016-01-01', '--end', '2016-02-01',
            '--output-file', tmp_file.name,
            '--email-to', 'foo@example.com',
            '--email-subject', 'The Email Subject')

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'Registrations by date', 0,
            [
                'MSISDN',
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
                '+2341111111111',
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

        [report_email] = mail.outbox
        self.assertEqual(report_email.subject, 'The Email Subject')
        (file_name, data, mimetype) = report_email.attachments[0]
        self.assertEqual('report-2016-01-01-to-2016-02-01.xlsx', file_name)
