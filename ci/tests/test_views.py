import json
import responses

from django.conf import settings
from django.test import TestCase, Client, override_settings

from ..views import get_identity_addresses


@override_settings(MESSAGES_PER_IDENTITY=100)
class ViewTests(TestCase):

    def setUp(self):
        self.client = Client()

    def login(self):
        self.client.login(username='testuser', password='testpass')
        session = self.client.session
        session['user_token'] = 'temptoken'
        session['user_permissions'] = [{"object_id": 1, "type": "ci:view"}]
        session['user_dashboards'] = []
        session.save()

    def set_session_user_tokens(self):
        session = self.client.session
        session['user_tokens'] = {
            "SEED_IDENTITY_SERVICE": {
                "url": 'http://idstore.example.com/', "token": 'idstoretoken'},
            "HUB": {
                "url": 'http://hub.example.com/', "token": 'hubtoken'},
            "SEED_STAGE_BASED_MESSAGING": {
                "url": 'http://sbm.example.com/', "token": 'sbmtoken'},
            "SEED_MESSAGE_SENDER": {
                "url": 'http://ms.example.com/', 'token': 'mstoken'
            }
        }
        session.save()

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
                },
                'created_at': '2016-01-01T10:30:21.0Z',
                'updated_at': '2016-01-01T10:30:21.0Z',
            },
            status=200,
            content_type='application/json')

    def add_registrations_callback(self):
        responses.add(
            responses.GET,
            "http://hub.example.com/registrations/?{}=operator_id".format(
                settings.IDENTITY_FIELD),
            match_querystring=True,
            json={
                'count': 0,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_changes_callback(self):
        responses.add(
            responses.GET,
            "http://hub.example.com/changes/?{}=operator_id".format(
                settings.IDENTITY_FIELD),
            match_querystring=True,
            json={
                'count': 0,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_subscriptions_callback(self):
        responses.add(
            responses.GET,
            "http://sbm.example.com/subscriptions/?identity=operator_id",
            match_querystring=True,
            json={
                'count': 0,
                'results': [],
            },
            status=200,
            content_type='application/json')

    def add_outbounds_callback(self, path='', num=1, metadata={},
                               next_msgs=None, prev_msgs=None):
        if next_msgs is not None:
            next_msgs = ('http://ms.example.com/outbound/?ordering='
                         '-created_at&limit=100&to_identity=operator_id&'
                         'offset={}'.format(next_msgs))
        if prev_msgs is not None:
            prev_msgs = ('http://ms.example.com/outbound/?ordering='
                         '-created_at&limit=100&to_identity=operator_id&'
                         'offset={}'.format(prev_msgs))
        outbounds = []

        for i in range(1, num+1):
            outbounds.append({
                'content': 'content',
                'delivered': True if i % 2 == 0 else False,
                'created_at': '2017-01-0{}T10:30:21.0Z'.format(i),
                'updated_at': '2017-01-0{}T10:30:21.0Z'.format(i),
                'metadata': metadata
            })

        responses.add(
            responses.GET,
            ('http://ms.example.com/outbound/?ordering=-created_at&limit=100'
             '&to_identity=operator_id{}'.format(path)),
            match_querystring=True,
            json={
                'count': num,
                'next': next_msgs,
                'previous': prev_msgs,
                'results': outbounds,
            },
            status=200,
            content_type='application/json')

    def add_inbounds_callback(
            self, path='', num=1, metadata={}, next_msgs=None, prev_msgs=None):
        if next_msgs is not None:
            next_msgs = ('http://ms.example.com/inbound/?ordering='
                         '-created_at&limit=100&from_identity=operator_id&'
                         'offset={}'.format(next_msgs))
        if prev_msgs is not None:
            prev_msgs = ('http://ms.example.com/indbound/?ordering='
                         '-created_at&limit=100&from_identity=operator_id&'
                         'offset={}'.format(prev_msgs))
        inbounds = []

        for i in range(1, num+1):
            inbounds.append({
                'content': 'content',
                'delivered': True if i % 2 == 0 else False,
                'created_at': '2017-01-0{}T10:30:21.0Z'.format(i),
                'updated_at': '2017-01-0{}T10:30:21.0Z'.format(i),
                'metadata': metadata
            })

        data = {
            'count': num,
            'next': next_msgs,
            'previous': prev_msgs,
            'results': inbounds,
        }

        responses.add(
            responses.GET,
            ('http://ms.example.com/inbound/?ordering=-created_at&limit=100'
             '&from_identity=operator_id{}'.format(path)),
            match_querystring=True,
            json=data,
            status=200,
            content_type='application/json')
        return data

    def add_messagesets_callback(self, count=0, results=[]):
        responses.add(
            responses.GET,
            'http://sbm.example.com/messageset/',
            json={
                'count': count,
                'results': results,
            },
            status=200,
            content_type='application/json')

    def add_messageset_language_callback(self):
        responses.add(
            responses.GET,
            'http://sbm.example.com/messageset_languages/',
            json={
                "2": ["afr_ZA", "eng_ZA"],
                "4": ["afr_ZA", "eng_ZA", "zul_ZA"]
            },
            status=200,
            content_type='application/json')

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

    @responses.activate
    def test_get_identity_outbound_display(self):
        self.login()
        self.set_session_user_tokens()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback(num=1, next_msgs=100, prev_msgs=0)
        self.add_inbounds_callback()

        response = self.client.get("/identities/operator_id/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sun 01 Jan 2017 10:30")

        # Check that the 'prev' and 'next' values returned are in the session
        session = self.client.session
        self.assertEqual(session['next_outbound_params'], {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]})
        self.assertEqual(session['prev_outbound_params'], {
            "limit": ["100"], "offset": ["0"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]})

    @responses.activate
    def test_get_identity_next_outbounds_display(self):
        self.login()
        self.set_session_user_tokens()
        session = self.client.session
        session['next_outbound_params'] = {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]}
        session.save()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback(num=1, path='&offset=100', next_msgs=200)
        self.add_inbounds_callback()

        # Navigate to the next page
        response = self.client.get("/identities/operator_id/?outbound_next",
                                   follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sun 01 Jan 2017 10:30")

        # Check that session 'next' value was overwritten
        session = self.client.session
        self.assertEqual(session['next_outbound_params'], {
            "limit": ["100"], "offset": ["200"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]})

    @responses.activate
    def test_get_identity_prev_outbounds_display(self):
        self.login()
        self.set_session_user_tokens()
        session = self.client.session
        session['prev_outbound_params'] = {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]}
        session.save()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback(num=1, path='&offset=100', prev_msgs=0)
        self.add_inbounds_callback()

        # Navigate to the previous page
        response = self.client.get("/identities/operator_id/?outbound_prev",
                                   follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sun 01 Jan 2017 10:30")

        # Check that session 'prev' value was overwritten
        session = self.client.session
        self.assertEqual(session['prev_outbound_params'], {
            "limit": ["100"], "offset": ["0"], "ordering": ["-created_at"],
            "to_identity": ["operator_id"]})

    @responses.activate
    def test_get_identity_inbounds_context(self):
        """
        When getting the details of an identity, that identity's inbound
        messages should be sent along in the context, so that the template can
        render them.
        """
        self.login()
        self.set_session_user_tokens()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback()
        inbounds = self.add_inbounds_callback(next_msgs=100)

        response = self.client.get("/identities/operator_id/", follow=True)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['inbounds'], inbounds)
        self.assertEqual(self.client.session['inbound_next_params'], {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]})
        self.assertEqual(self.client.session['inbound_prev_params'], {})

    @responses.activate
    def test_get_identity_next_inbounds_context(self):
        """
        When getting the details of an identity, if the next page for the
        inbound messages is requested, the next page should be sent along in
        the context.
        """
        self.login()
        self.set_session_user_tokens()
        session = self.client.session
        session['inbound_next_params'] = {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]}
        session.save()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback()
        inbounds = self.add_inbounds_callback(
            next_msgs=200, prev_msgs=0, path='&offset=100')

        response = self.client.get(
            "/identities/operator_id/?inbound_next=true", follow=True)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['inbounds'], inbounds)
        self.assertEqual(self.client.session['inbound_next_params'], {
            "limit": ["100"], "offset": ["200"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]})
        self.assertEqual(self.client.session['inbound_prev_params'], {
            "limit": ["100"], "offset": ["0"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]})

    @responses.activate
    def test_get_identity_previous_inbounds_context(self):
        """
        When getting the details of an identity, if the previous page for the
        inbound messages is requested, the previous page should be sent along
        in the context.
        """
        self.login()
        self.set_session_user_tokens()
        session = self.client.session
        session['inbound_prev_params'] = {
            "limit": ["100"], "offset": ["200"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]}
        session.save()

        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_subscriptions_callback()
        self.add_outbounds_callback()
        inbounds = self.add_inbounds_callback(
            next_msgs=300, prev_msgs=100, path='&offset=200')

        response = self.client.get(
            "/identities/operator_id/?inbound_prev=true", follow=True)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['inbounds'], inbounds)
        self.assertEqual(self.client.session['inbound_next_params'], {
            "limit": ["100"], "offset": ["300"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]})
        self.assertEqual(self.client.session['inbound_prev_params'], {
            "limit": ["100"], "offset": ["100"], "ordering": ["-created_at"],
            "from_identity": ["operator_id"]})

    @responses.activate
    def test_optout_identity(self):
        self.login()
        self.set_session_user_tokens()
        self.add_messagesets_callback()
        self.add_identity_callback()
        self.add_registrations_callback()
        self.add_changes_callback()
        self.add_outbounds_callback()
        self.add_inbounds_callback()

        subscription = {
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
        }

        responses.add(
            responses.GET,
            'http://sbm.example.com/subscriptions/?identity=operator_id',
            match_querystring=True,
            json={
                'count': 1,
                'next': None,
                'results': [subscription],
            },
            status=200,
            content_type='application/json')

        responses.add(
            responses.POST,
            'http://idstore.example.com/optout/',
            json={
                "identity": "operator_id",
                "optout_type": "stop",
                "address_type": "msisdn",
                "address": "+2340000000000",
                "request_source": "ci"},
            status=200,
            content_type='application/json')

        responses.add(
            responses.POST,
            'http://hub.example.com/optout_admin/',
            json={"mother_id": "operator_id"},
            status=201,
            content_type='application/json'
        )

        response = self.client.post(
            "/identities/operator_id/",
            {"optout_identity": ['']})

        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertEqual(messages[0].message, 'Successfully opted out.')

    @responses.activate
    def test_change_subscription(self):
        self.login()
        self.set_session_user_tokens()

        subscription_id = "sub12312-63e2-4acc-9b94-26663b9bc267"
        identity_id = "mother01-63e2-4acc-9b94-26663b9bc267"

        self.add_messagesets_callback(count=2, results=[
            {"id": 2, "short_name": "test"},
            {"id": 4, "short_name": "test2"}
        ])
        self.add_messageset_language_callback()

        responses.add(
            responses.POST,
            'http://hub.example.com/change_admin/',
            json={
                "mother_id": identity_id,
                "subscription": subscription_id
            },
            status=201,
            content_type='application/json'
        )
        responses.add(
            responses.GET,
            "http://sbm.example.com/subscriptions/%s/" % subscription_id,
            match_querystring=True,
            json={
                "id": subscription_id,
                "identity": identity_id,
                "active": True,
                "completed": False,
                "lang": "eng_ZA",
                "messageset": 2,
                "next_sequence_number": 32,
                "schedule": 132,
                "process_status": 0,
                "version": 1,
                "metadata": {},
                "created_at": "2015-07-10T06:13:29.693272Z",
                "updated_at": "2015-07-10T06:13:29.693272Z"
            },
            status=200,
            content_type='application/json')

        response = self.client.post(
            "/subscriptions/%s/" % subscription_id,
            {
                "language": "zul_ZA",
                "messageset": 4
            })

        self.assertEqual(response.status_code, 200)

        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message, 'Successfully added change.')

        change_request = responses.calls[2].request
        self.assertEqual(change_request.url,
                         "http://hub.example.com/change_admin/")
        self.assertEqual(
            json.loads(change_request.body),
            {
                "mother_id": identity_id,
                "messageset": "test2",
                "language": "zul_ZA",
                "subscription": subscription_id
            })

    @responses.activate
    @override_settings(METRIC_API_URL='http://metrics-api.org/')
    def test_dashboard_metric(self):
        """
        When requesting a dashboard widget the metric api must be called and
        data must be returned in the correct format
        """
        self.login()
        self.set_session_user_tokens()

        responses.add(
            responses.GET,
            "http://metrics-api.org/metrics/?start=-30d&interval=1d&"
            "m=one.total.sum&m=two.total.sum&m=three.total.sum&nulls=zeroize",
            match_querystring=True,
            json={
                'one.total.sum': [{'y': 1.0, 'x': 111}, {'y': 2.0, 'x': 222}],
                'two.total.sum': [{'y': 4.0, 'x': 333}, {'y': 5.0, 'x': 444}],
                'three.total.sum': [{'y': 6.0, 'x': 123}, {'y': 7.0, 'x': 321}]
            },
            status=200,
            content_type='application/json'
        )

        response = self.client.get(
            "/api/v1/metric/?start=-30d&interval=1d&m=one.total.sum&m="
            "two.total.sum&m=three.total.sum&nulls=zeroize",
            follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content.decode('utf-8')), {
            "objects": [{
                    "values": [{"y": 1.0, "x": 111}, {"y": 2.0, "x": 222}],
                    "key": "one.total.sum"
                }, {
                    "values": [{"y": 4.0, "x": 333}, {"y": 5.0, "x": 444}],
                    "key": "two.total.sum"
                }, {
                    "values": [{"y": 6.0, "x": 123}, {"y": 7.0, "x": 321}],
                    "key": "three.total.sum"
                }
            ]})