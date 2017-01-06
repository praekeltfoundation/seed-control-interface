import responses

from tempfile import NamedTemporaryFile
from datetime import datetime

import pytz
from openpyxl import load_workbook

from django.test import TestCase, Client, override_settings
from django.core import mail
from django.core.management import call_command
from ci.management.commands.generate_reports import parse_cursor_params
from .views import get_identity_addresses
from . import utils


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


class UtilsTests(TestCase):

    def test_transform_timeseries_data(self):
        ts = {
            u'subscriptions.created.sum': [
                {'x': 1483297200000, 'y': 9.0},
                {'x': 1483300800000, 'y': 5.0},
                {'x': 1483304400000, 'y': 1.0},
                {'x': 1483308000000, 'y': 1.0},
                {'x': 1483311600000, 'y': 1.0},
                {'x': 1483315200000, 'y': 1.0},
                {'x': 1483318800000, 'y': 0.0},
                {'x': 1483322400000, 'y': 0.0},
                {'x': 1483326000000, 'y': 2.0},
                {'x': 1483329600000, 'y': 1.0},
                {'x': 1483333200000, 'y': 3.0},
                {'x': 1483336800000, 'y': 10.0},
                {'x': 1483340400000, 'y': 22.0},
                {'x': 1483344000000, 'y': 143.0},
                {'x': 1483347600000, 'y': 102.0},
                {'x': 1483351200000, 'y': 86.0},
                {'x': 1483354800000, 'y': 86.0},
                {'x': 1483358400000, 'y': 91.0},
                {'x': 1483362000000, 'y': 87.0},
                {'x': 1483365600000, 'y': 91.0},
                {'x': 1483369200000, 'y': 107.0},
                {'x': 1483372800000, 'y': 109.0},
                {'x': 1483376400000, 'y': 137.0},
                {'x': 1483380000000, 'y': 626.0},
                {'x': 1483383600000, 'y': 43.0},
                {'x': 1483387200000, 'y': 24.0},
                {'x': 1483390800000, 'y': 15.0},
                {'x': 1483394400000, 'y': 3.0},
                {'x': 1483398000000, 'y': 0.0},
                {'x': 1483401600000, 'y': 2.0},
                {'x': 1483405200000, 'y': 1.0},
                {'x': 1483408800000, 'y': 1.0},
                {'x': 1483412400000, 'y': 5.0},
                {'x': 1483416000000, 'y': 4.0},
                {'x': 1483419600000, 'y': 23.0},
                {'x': 1483423200000, 'y': 13.0}
            ]
        }

        # Test start only
        r1 = utils.transform_timeseries_data(ts, 1483308000000)
        self.assertEqual(len(r1), 33)

        # Test start and end
        r2 = utils.transform_timeseries_data(ts, 1483308000000, 1483326000000)
        self.assertEqual(len(r2), 6)

        # Test data format
        self.assertEqual(r2, [1.0, 1.0, 1.0, 0.0, 0.0, 2.0])

    def test_get_last_value_from_timeseries(self):
        ts = {
            'subscriptions.send.estimate.1.last': [
                {'x': 1482796800000, 'y': 2538.0},
                {'x': 1482883200000, 'y': 2515.0},
                {'x': 1482969600000, 'y': 2542.0},
                {'x': 1483056000000, 'y': 2532.0}
            ]
        }

        r1 = utils.get_last_value_from_timeseries(ts)
        self.assertEqual(r1, 2532.0)

        r2 = utils.get_last_value_from_timeseries({})
        self.assertEqual(r2, 0)

    def test_week_from_datetime(self):
        tz = pytz.timezone('Africa/Johannesburg')
        utc = pytz.timezone('UTC')
        d1 = tz.localize(datetime(2016, 12, 5, 8, 15, 0, 0))
        r1 = utils.DTBoundry.week_from_datetime(d1)
        self.assertIsInstance(r1, utils.DTBoundry)
        self.assertEqual(
            r1.start,
            utc.localize(datetime(2016, 12, 5, 0, 0, 0, 0))
        )
        self.assertEqual(
            r1.end,
            utc.localize(datetime(2016, 12, 11, 0, 0, 0, 0))
        )

    def test_day_from_datetime(self):
        tz = pytz.timezone('Africa/Johannesburg')
        utc = pytz.timezone('UTC')
        d1 = tz.localize(datetime(2016, 12, 5, 8, 15, 0, 0))
        r1 = utils.DTBoundry.day_from_datetime(d1)
        self.assertIsInstance(r1, utils.DTBoundry)
        self.assertEqual(
            r1.start,
            utc.localize(datetime(2016, 12, 4, 22, 0, 0, 0))
        )
        self.assertEqual(
            r1.end,
            utc.localize(datetime(2016, 12, 5, 21, 0, 0, 0))
        )
