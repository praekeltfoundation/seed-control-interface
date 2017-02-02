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

    def add_blank_registration_callback(self, next_='?foo=bar'):
        if next_:
            next_ = 'http://hub.example.com/registrations/{}'.format(next_)

        responses.add(
            responses.GET,
            ("http://hub.example.com/registrations/?"
             "created_before=2016-02-01T00%3A00%3A00%2B00%3A00"
             "&created_after=2016-01-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 0,
                'next': next_,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_registrations_callback(self, path='?foo=bar', num=1):
        registrations = [{
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
            }] * num

        responses.add(
            responses.GET,
            'http://hub.example.com/registrations/{}'.format(path),
            match_querystring=True,
            json={
                'count': num,
                'next': None,
                'results': registrations,
            },
            status=200,
            content_type='application/json')

    def add_blank_changes_callback(self, next_='?foo=bar'):
        if next_:
            next_ = 'http://hub.example.com/changes/{}'.format(next_)

        responses.add(
            responses.GET,
            ("http://hub.example.com/changes/?"
             "action=change_loss"
             "&created_before=2016-02-01T00%3A00%3A00%2B00%3A00"
             "&created_after=2016-01-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 0,
                'next': next_,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_changes_callback(self, path='?foo=bar', num=1):
        changes = [{
            "id": "b13e7b77-9ff6-4099-b87e-38d450f5b8cf",
            "action": "change_loss",
            "mother_id": "8311c23d-f3c4-4cab-9e20-5208d77dcd1b",
            "data": {},
            "validated": True,
            "source": 1,
            "created_at": "2017-01-27T10:00:06.354178Z",
            "updated_at": "2017-01-27T10:00:06.354178Z",
            "created_by": 1,
            "updated_by": 1
        }] * num

        responses.add(
            responses.GET,
            "http://hub.example.com/changes/{}".format(path),
            match_querystring=True,
            json={
                'count': num,
                'next': None,
                'results': changes,
            },
            status=200,
            content_type='application/json')

    def add_identity_callback(self, identity='operator_id'):
        responses.add(
            responses.GET,
            'http://idstore.example.com/identities/{}/'.format(identity),
            json={
                'identity': identity,
                'details': {
                    'personnel_code': 'personnel_code',
                    'facility_name': 'facility_name',
                    'default_addr_type': 'msisdn',
                    'receiver_role': 'role',
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

    def add_blank_subscription_callback(self, next_='?foo=bar'):
        if next_:
            next_ = 'http://sbm.example.com/subscriptions/{}'.format(next_)

        responses.add(
            responses.GET,
            ("http://sbm.example.com/subscriptions/?"
             "created_before=2016-02-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 0,
                'next': next_,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_subscriptions_callback(self, path='?foo=bar', num=1):
        subscriptions = [{
            'lang': 'eng_NG',
            'created_at': '2016-11-22T08:12:45.343829Z',
            'messageset': 4,
            'schedule': 5,
            'url': 'url',
            'completed': False,
            'initial_sequence_number': 1,
            'updated_at': '2016-11-22T08:12:52.411545Z',
            'version': 1,
            'next_sequence_number': 1,
            'process_status': 0,
            'active': True,
            'id': '10176584-2a47-42b6-b9f3-a3a98070f35e',
            'identity': '17cf37cf-edd6-4634-88e3-f793575f7e3a',
            'metadata': {
                'scheduler_schedule_id':
                    'a64d153f-1515-42c1-997a-9a3444c916fc'
            }
        }] * num

        responses.add(
            responses.GET,
            'http://sbm.example.com/subscriptions/{}'.format(path),
            match_querystring=True,
            json={
                'count': num,
                'next': None,
                'results': subscriptions,
            },
            status=200,
            content_type='application/json')

    def add_blank_outbound_callback(self, next_='?foo=bar'):
        if next_:
            next_ = 'http://ms.example.com/outbound/{}'.format(next_)

        responses.add(
            responses.GET,
            ("http://ms.example.com/outbound/?"
             "created_before=2016-02-01T00%3A00%3A00%2B00%3A00"
             "&created_after=2016-01-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 0,
                'next': next_,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_outbound_callback(self, path='?foo=bar', num=1):
        outbounds = []

        for i in range(0, num):
            outbounds.append({
                'to_addr': 'addr',
                'content': 'content',
                'delivered': True if i % 2 == 0 else False,
                'created_at': '2016-01-01T10:30:21.{}Z'.format(i)
            })

        responses.add(
            responses.GET,
            'http://ms.example.com/outbound/?foo=bar',
            match_querystring=True,
            json={
                'count': num,
                'next': None,
                'results': outbounds,
            },
            status=200,
            content_type='application/json')

    def add_messageset_callback(self):
        responses.add(
            responses.GET,
            'http://sbm.example.com/messageset/4/',
            json={
                'created_at': '2016-06-22T10:30:21.186435Z',
                'short_name': 'prebirth.mother.audio.10_42.tue_thu.9_11',
                'next_set': 11,
                'notes': '',
                'updated_at': '2016-09-13T13:01:32.591754Z',
                'default_schedule': 5,
                'content_type': 'audio',
                'id': 4
            },
            status=200,
            content_type='application/json')

    def add_blank_optouts_callback(self, next_='?foo=bar'):
        if next_:
            next_ = 'http://idstore.example.com/optouts/search/{}'.format(
                next_)

        responses.add(
            responses.GET,
            ("http://idstore.example.com/optouts/search/?"
             "created_at__lte=2016-02-01T00%3A00%3A00%2B00%3A00&"
             "created_at__gte=2016-01-01T00%3A00%3A00%2B00%3A00"),
            match_querystring=True,
            json={
                'count': 0,
                'next': next_,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_optouts_callback(self, path='?foo=bar', num=1):
        optouts = [{
            "id": "e5210c99-8d8a-40f1-8e7f-8a66c4de9e29",
            "optout_type": "stop",
            "identity": "8311c23d-f3c4-4cab-9e20-5208d77dcd1b",
            "address_type": "msisdn",
            "address": "+1234",
            "request_source": "testsource",
            "requestor_source_id": "1",
            "reason": "Test reason",
            "created_at": "2017-01-27T10:00:06.354178Z"
        }] * num

        responses.add(
            responses.GET,
            'http://idstore.example.com/optouts/search/{}'.format(path),
            match_querystring=True,
            json={
                'count': num,
                'next': None,
                'results': optouts,
            },
            status=200,
            content_type='application/json')

    def generate_report(self):
        tmp_file = self.mk_tempfile()

        call_command(
            'generate_reports',
            '--start', '2016-01-01', '--end', '2016-02-01',
            '--output-file', tmp_file.name,
            '--email-to', 'foo@example.com',
            '--email-subject', 'The Email Subject',
            '--sbm-url', 'http://sbm.example.com/',
            '--sbm-token', 'sbmtoken',
            '--ms-url', 'http://ms.example.com/',
            '--ms-token', 'mstoken')

        return tmp_file

    @responses.activate
    def test_generate_report_email(self):
        """
        Generating a report should create an email with the correct address,
        subject, and attachment.
        """
        self.add_blank_registration_callback(next_=None)
        self.add_blank_subscription_callback(next_=None)
        self.add_blank_outbound_callback(next_=None)
        self.add_blank_optouts_callback(next_=None)
        self.add_blank_changes_callback(next_=None)
        self.generate_report()
        [report_email] = mail.outbox
        self.assertEqual(report_email.subject, 'The Email Subject')
        (file_name, data, mimetype) = report_email.attachments[0]
        self.assertEqual('report-2016-01-01-to-2016-02-01.xlsx', file_name)

    @responses.activate
    def test_generate_report_registrations(self):
        """
        When generating a report, the first tab should be a list of
        registrations with the relevant registration details.
        """
        # Registrations, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_registration_callback()

        # Registrations, second page, this one has the results
        self.add_registrations_callback()

        # HCW Identity
        self.add_identity_callback()

        # Receiver Identity
        self.add_identity_callback('receiver_id')

        # Subscriptions, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_subscription_callback(next_=None)

        self.add_subscriptions_callback()

        self.add_messageset_callback()

        self.add_identity_callback('17cf37cf-edd6-4634-88e3-f793575f7e3a')

        self.add_blank_outbound_callback(next_=None)

        self.add_outbound_callback()

        # No opt outs, we're not testing optout by subscription
        self.add_blank_optouts_callback(next_=None)
        self.add_blank_changes_callback(next_=None)

        tmp_file = self.generate_report()

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
                '+2340000000000',
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
                None,
                'state',
            ])

    @responses.activate
    def test_generate_report_health_worker_registrations(self):
        """
        When generating a report, the second tab should be registrations per
        health worker, and it should have the correct information.
        """
        # Registrations, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_registration_callback()

        # Registrations, second page, this one has the results
        # 2 registrations for 1 operator
        self.add_registrations_callback(num=2)

        # Identity for hcw
        self.add_identity_callback('operator_id')

        # identity for receiver, for first report
        self.add_identity_callback('receiver_id')

        # Subscriptions, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_subscription_callback(next_=None)

        self.add_subscriptions_callback(num=2)

        self.add_messageset_callback()

        self.add_identity_callback('17cf37cf-edd6-4634-88e3-f793575f7e3a')

        self.add_blank_outbound_callback(next_=None)

        self.add_outbound_callback()

        # No opt outs, we're not testing optout by subscription
        self.add_blank_optouts_callback(next_=None)
        self.add_blank_changes_callback(next_=None)

        tmp_file = self.generate_report()

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'Health worker registrations', 0,
            [
                'Unique Personnel Code',
                'Facility',
                'State',
                'Cadre',
                'Number of Registrations',
            ])

        # Assert 1 row is written
        self.assertSheetRow(
            tmp_file.name, 'Health worker registrations', 1,
            [
                'personnel_code',
                'facility_name',
                'state',
                'role',
                2,
            ])

    @responses.activate
    def test_generate_report_enrollments(self):
        """
        When generating a report, the third tab should be enrollments,
        and it should have the correct information.
        """
        # Registrations, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_registration_callback()

        # Registrations, second page, this one has the results
        # 2 registrations for 1 operator
        self.add_registrations_callback(num=2)

        # Identity for hcw
        self.add_identity_callback('operator_id')

        # identity for receiver, for first report
        self.add_identity_callback('receiver_id')

        # Subscriptions, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_subscription_callback()

        self.add_subscriptions_callback(num=2)

        self.add_messageset_callback()

        self.add_identity_callback('17cf37cf-edd6-4634-88e3-f793575f7e3a')

        self.add_blank_outbound_callback(next_=None)

        self.add_outbound_callback()

        # No opt outs, we're not testing optout by subscription
        self.add_blank_optouts_callback(next_=None)
        self.add_blank_changes_callback(next_=None)

        tmp_file = self.generate_report()

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'Enrollments', 0,
            [
                'Message set',
                'Roleplayer',
                'Total enrolled',
                'Enrolled in period',
                'Enrolled and opted out in period',
                'Enrolled and completed in period',
            ])

        # Assert 1 row is written
        self.assertSheetRow(
            tmp_file.name, 'Enrollments', 1,
            ['prebirth', 'role', 2, 2, 0, 0])

    @responses.activate
    def test_generate_report_sms_per_msisdn(self):
        """
        When generating a report, the fourth tab should be SMS delivery per
        MSISDN, and it should have the correct information.
        """
        # Registrations, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_registration_callback()

        # Registrations, second page, this one has the results
        # 2 registrations for 1 operator
        self.add_registrations_callback(num=2)

        # Identity for hcw
        self.add_identity_callback('operator_id')

        # identity for receiver, for first report
        self.add_identity_callback('receiver_id')

        # Subscriptions, first page, just returns empty results to make sure
        # we're actually paging through the results sets using the `next`
        # parameter
        self.add_blank_subscription_callback()

        self.add_subscriptions_callback()

        self.add_messageset_callback()

        self.add_identity_callback('17cf37cf-edd6-4634-88e3-f793575f7e3a')

        self.add_blank_outbound_callback()

        self.add_outbound_callback(num=4)

        # No opt outs, we're not testing optout by subscription
        self.add_blank_optouts_callback(next_=None)
        self.add_blank_changes_callback(next_=None)

        tmp_file = self.generate_report()

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'SMS delivery per MSISDN', 0,
            [
                'MSISDN',
                'SMS 1',
                'SMS 2',
                'SMS 3',
                'SMS 4'
            ])

        # Assert 1 row is written
        self.assertSheetRow(
            tmp_file.name, 'SMS delivery per MSISDN', 1,
            ['addr', 'Yes', 'No', 'Yes', 'No'])

    @responses.activate
    def test_generate_report_optout_by_subscription(self):
        # Return no registrations or subscriptions for other reports
        self.add_blank_registration_callback(next_=None)
        self.add_blank_subscription_callback(next_=None)

        # Optouts, first page no results to make sure that we're paging
        self.add_blank_optouts_callback()
        self.add_optouts_callback()

        # Add identity for optout
        self.add_identity_callback('8311c23d-f3c4-4cab-9e20-5208d77dcd1b')

        # Add subscription result for identity
        self.add_subscriptions_callback(
            path=(
                '?active=False&completed=False&'
                'created_before=2017-01-27T10%3A00%3A06.354178Z&'
                'identity=8311c23d-f3c4-4cab-9e20-5208d77dcd1b')
        )

        # Add messageset for subscription
        self.add_messageset_callback()

        self.add_blank_outbound_callback(next_=None)
        self.add_blank_changes_callback(next_=None)
        self.add_registrations_callback(
            path='?receiver_id=8311c23d-f3c4-4cab-9e20-5208d77dcd1b'
            '&created_before=2017-01-27T10%3A00%3A06.354178Z', num=0)

        tmp_file = self.generate_report()

        # Assert headers are set
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Subscription', 0,
            [
                "Timestamp",
                "Subscription Message Set",
                "Receiver's Role",
                "Reason",
            ])

        # Assert row 1 is written
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Subscription', 1,
            [
                "2017-01-27T10:00:06.354178Z",
                "prebirth.mother.audio.10_42.tue_thu.9_11",
                "role",
                "Test reason",
            ])

        # Assert that warning is written
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Subscription', 2,
            [
                "NOTE: The message set is not guaranteed to be correct, as "
                "the current structure of the data does not allow us to link "
                "the opt out to a subscription, so this is a best-effort "
                "guess.",
                None,
                None,
                None,
            ])

    @responses.activate
    def test_generate_report_optouts_by_date(self):
        # Return no registrations or subscriptions for other reports
        self.add_blank_registration_callback(next_=None)
        self.add_blank_subscription_callback(next_=None)
        self.add_blank_outbound_callback(next_=None)

        # Optouts, first page no results to make sure that we're paging
        self.add_blank_optouts_callback()
        self.add_optouts_callback()

        # Callbacks for identities
        self.add_identity_callback('8311c23d-f3c4-4cab-9e20-5208d77dcd1b')

        # Callbacks for stage based messaging
        self.add_subscriptions_callback(
            '?active=False&completed=False&'
            'created_before=2017-01-27T10%3A00%3A06.354178Z&'
            'identity=8311c23d-f3c4-4cab-9e20-5208d77dcd1b')
        self.add_messageset_callback()

        # Callbacks for registrations
        self.add_registrations_callback(
            '?receiver_id=8311c23d-f3c4-4cab-9e20-5208d77dcd1b&'
            'created_before=2017-01-27T10%3A00%3A06.354178Z')

        # Changes, first page no results to make sure that we're paging
        self.add_blank_changes_callback()
        self.add_changes_callback()

        tmp_file = self.generate_report()
        # Check headers
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Date', 0,
            [
                "Timestamp",
                "Registered Receiver",
                "Opt Out Reason",
                "Loss Subscription",
                "Opt Out Receiver",
                "Message Sets",
                "Receivers",
                "Number of Receivers",
            ]
        )
        # Check optout from optout
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Date', 1,
            [
                "2017-01-27T10:00:06.354178Z",
                "msg_receiver",
                "Test reason",
                None,
                "role messages",
                "prebirth.mother.audio.10_42.tue_thu.9_11",
                "role",
                1,
            ]
        )
        # Check optout from change
        self.assertSheetRow(
            tmp_file.name, 'Opt Outs by Date', 2,
            [
                "2017-01-27T10:00:06.354178Z",
                "msg_receiver",
                "miscarriage",
                "Yes",
                "role messages",
                "prebirth.mother.audio.10_42.tue_thu.9_11",
                "role",
                1,
            ]
        )


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
