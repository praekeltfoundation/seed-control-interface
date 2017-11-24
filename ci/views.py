from functools import wraps
import logging
import json
from datetime import timedelta

from demands import HTTPServiceError
from django.shortcuts import render, redirect, resolve_url
from django.utils.decorators import available_attrs
from django.utils.six.moves.urllib.parse import urlparse
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.sites.shortcuts import get_current_site
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.urlresolvers import reverse
from django.utils.http import is_safe_url
from django.utils.timezone import now
from django.http import HttpResponseRedirect, JsonResponse
from django.template.defaulttags import register
from django.template.response import TemplateResponse
from django.core.context_processors import csrf
from django.conf import settings
from django import forms
import dateutil.parser

from seed_services_client import (
    ControlInterfaceApiClient,
    HubApiClient,
    IdentityStoreApiClient,
    MessageSenderApiClient,
    SchedulerApiClient,
    StageBasedMessagingApiClient,
)
from seed_services_client.metrics import MetricsApiClient

from urlobject import URLObject

from .forms import (AuthenticationForm, IdentitySearchForm,
                    RegistrationFilterForm, SubscriptionFilterForm,
                    ChangeFilterForm, ReportGenerationForm,
                    AddSubscriptionForm, DeactivateSubscriptionForm,
                    ChangeSubscriptionForm, MsisdnReportGenerationForm)
from . import utils

logger = logging.getLogger(__name__)


@register.filter
def get_identity_addresses(identity):
    details = identity.get('details', {})
    default_addr_type = details.get('default_addr_type', None)
    addresses = details.get('addresses', {})
    if not default_addr_type:
        logger.warning('No default_addr_type specified for: %r' % (identity,))
        return {}
    return addresses.get(default_addr_type, {})


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_date(date_string):
    if date_string is not None:
        return dateutil.parser.parse(date_string)


@register.simple_tag
def replace_query_param(url, parameter, value):
    url = URLObject(url)
    return url.set_query_params([(parameter, value)])


ciApi = ControlInterfaceApiClient(
    api_url=settings.CONTROL_INTERFACE_SERVICE_URL,
    auth_token=settings.CONTROL_INTERFACE_SERVICE_TOKEN
)


def request_passes_test(test_func, login_url=None,
                        redirect_field_name=REDIRECT_FIELD_NAME):
    """
    Decorator for views that checks that the request passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the requst object and returns True if the request passes.
    """

    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            if test_func(request):
                return view_func(request, *args, **kwargs)
            path = request.build_absolute_uri()
            resolved_login_url = resolve_url(login_url or settings.LOGIN_URL)
            # If the login url is the same scheme and net location then just
            # use the path as the "next" url.
            login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
            current_scheme, current_netloc = urlparse(path)[:2]
            if ((not login_scheme or login_scheme == current_scheme) and
                    (not login_netloc or login_netloc == current_netloc)):
                path = request.get_full_path()
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(
                path, resolved_login_url, redirect_field_name)
        return _wrapped_view
    return decorator


def login_required(function=None, redirect_field_name=REDIRECT_FIELD_NAME,
                   login_url=None):
    """
    Decorator for views that checks that the user is logged in, redirecting
    to the log-in page if necessary.
    """
    actual_decorator = request_passes_test(
        lambda r: r.session.get('user_token'),
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function)
    return actual_decorator


def has_permission(permissions, permission, object_id=None):
    ids = [p['object_id'] for p in permissions if p['type'] == permission]
    if object_id is None and len(ids) == 1:
        return True
    elif object_id is not None and object_id in ids:
        return True
    return False


def permission_required(function=None, permission=None, object_id=None,
                        redirect_field_name=REDIRECT_FIELD_NAME,
                        login_url=None):
    """
    Decorator for views that checks that the user is logged in, redirecting
    to the log-in page if necessary.
    """
    actual_decorator = request_passes_test(
        lambda r: has_permission(r.session.get('user_permissions'), permission, object_id),  # noqa
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function)
    return actual_decorator


def tokens_required(service_list):
    """
    Ensure the user has the necessary tokens for the specified services
    """
    def decorator(func):
        @wraps(func)
        def inner(request, *args, **kwargs):
            for service in service_list:
                if service not in request.session["user_tokens"]:
                    return redirect('denied')
            return func(request, *args, **kwargs)
        return inner
    return decorator


def login(request, template_name='ci/login.html',
          redirect_field_name=REDIRECT_FIELD_NAME,
          authentication_form=AuthenticationForm):
    """
    Displays the login form and handles the login action.
    """
    redirect_to = request.POST.get(redirect_field_name,
                                   request.GET.get(redirect_field_name, ''))

    if request.method == "POST":
        form = authentication_form(request, data=request.POST)
        if form.is_valid():

            # Ensure the user-originating redirection url is safe.
            if not is_safe_url(url=redirect_to, host=request.get_host()):
                redirect_to = resolve_url(settings.LOGIN_REDIRECT_URL)

            # Okay, security check complete. Get the user object from auth api.
            user = form.get_user()
            request.session['user_token'] = user["token"]
            request.session['user_email'] = user["email"]
            request.session['user_permissions'] = user["permissions"]
            request.session['user_id'] = user["id"]

            # Set user dashboards because they are slow to change
            dashboards = ciApi.get_user_dashboards(user["id"])
            dashboard_list = list(dashboards['results'])
            if len(dashboard_list) > 0:
                request.session['user_dashboards'] = \
                    dashboard_list[0]["dashboards"]
                request.session['user_default_dashboard'] = \
                    dashboard_list[0]["default_dashboard"]["id"]
            else:
                request.session['user_dashboards'] = []
                request.session['user_default_dashboard'] = None

            # Get the user access tokens too and format for easy access
            tokens = ciApi.get_user_service_tokens(
                params={"user_id": user["id"]})
            token_list = list(tokens['results'])
            user_tokens = {}
            if len(token_list) > 0:
                for token in token_list:
                    user_tokens[token["service"]["name"]] = {
                        "token": token["token"],
                        "url": token["service"]["url"] + "/api/v1"
                    }
            request.session['user_tokens'] = user_tokens

            return HttpResponseRedirect(redirect_to)
    else:
        form = authentication_form(request)

    current_site = get_current_site(request)

    context = {
        'form': form,
        redirect_field_name: redirect_to,
        'site': current_site,
        'site_name': current_site.name,
    }

    return TemplateResponse(request, template_name, context)


def logout(request):
    try:
        del request.session['user_token']
        del request.session['user_email']
        del request.session['user_permissions']
        del request.session['user_id']
        del request.session['user_dashboards']
        del request.session['user_default_dashboard']
    except KeyError:
        pass
    return redirect('index')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def index(request):
    if "user_default_dashboard" in request.session and \
            request.session["user_default_dashboard"] is not None:
        return HttpResponseRedirect(reverse('dashboard', args=(
            request.session["user_default_dashboard"],)))
    else:
        return render(request, 'ci/index.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_messages(request):
    if request.is_ajax():
        METRIC_SENT_SUM = 'message.sent.sum'
        client = MetricsApiClient(
            settings.METRIC_API_URL,
            auth=(settings.METRIC_API_USER, settings.METRIC_API_PASSWORD))
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'estimated-vs-sent':
            get_days = today.weekday() + 1
            sent = client.get_metrics(
                m=METRIC_SENT_SUM, from_='-%sd' % get_days, interval='1d',
                nulls='zeroize')
            sent_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='week')

            # The estimate data is stored as .last metrics with 0 - 6
            # representing the days of the week. The cron format specifies
            # 0 = Sunday whereas Python datetime.weekday() specifies
            # 0 = Monday.
            estimate_data = []
            for day in range(7):
                estimated = client.get_metrics(
                    m='subscriptions.send.estimate.%s.last' % day, from_='-7d',
                    interval='1d', nulls='zeroize')
                estimate_data.append(
                    utils.get_last_value_from_timeseries(estimated))
            return JsonResponse({
                'Estimated': estimate_data,
                'Sent': sent_data
            })

        elif chart_type == 'sent-today':
            get_hours = today.hour
            sent = client.get_metrics(
                m=METRIC_SENT_SUM, from_='-%sh' % get_hours, interval='1h',
                nulls='zeroize')
            sent_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='day')
            return JsonResponse({
                'Today': sent_data
            })

        elif chart_type == 'sent-this-week':
            get_days = today.weekday() + 7  # Include last week in the set.
            sent = client.get_metrics(
                m=METRIC_SENT_SUM, from_='-%sd' % get_days, interval='1d',
                nulls='zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                sent, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    return render(request, 'ci/health_messages.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_subscriptions(request):
    if request.is_ajax():
        METRIC_SUBSCRIPTIONS_SUM = 'subscriptions.created.sum'
        client = MetricsApiClient(
            settings.METRIC_API_URL,
            auth=(settings.METRIC_API_USER, settings.METRIC_API_PASSWORD))
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'subscriptions-today':
            get_hours = today.hour + 24  # Include yesterday in the set.
            subscriptions = client.get_metrics(
                m=METRIC_SUBSCRIPTIONS_SUM, from_='-%sh' % get_hours,
                interval='1h', nulls='zeroize')
            today_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today, range_type='day')
            yesterday_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today - timedelta(days=1), range_type='day')
            return JsonResponse({
                'Yesterday': yesterday_data,
                'Today': today_data
            })

        elif chart_type == 'subscriptions-this-week':
            get_days = today.weekday() + 7  # Include last week in the set.
            subscriptions = client.get_metrics(
                m=METRIC_SUBSCRIPTIONS_SUM, from_='-%sd' % get_days,
                interval='1d', nulls='zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    return render(request, 'ci/health_subscriptions.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_registrations(request):
    if request.is_ajax():
        METRIC_REGISTRATIONS_SUM = 'registrations.created.sum'
        client = MetricsApiClient(
            settings.METRIC_API_URL,
            auth=(settings.METRIC_API_USER, settings.METRIC_API_PASSWORD))
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'registrations-today':
            get_hours = today.hour + 24  # Include yesterday in the set.
            registrations = client.get_metrics(
                m=METRIC_REGISTRATIONS_SUM, from_='-%sh' % get_hours,
                interval='1h', nulls='zeroize')
            today_data = utils.get_ranged_data_from_timeseries(
                registrations, today, range_type='day')
            yesterday_data = utils.get_ranged_data_from_timeseries(
                registrations, today - timedelta(days=1), range_type='day')
            return JsonResponse({
                'Yesterday': yesterday_data,
                'Today': today_data
            })

        elif chart_type == 'registrations-this-week':
            get_days = today.weekday() + 7  # Include last week in the set.
            registrations = client.get_metrics(
                m=METRIC_REGISTRATIONS_SUM, from_='-%sd' % get_days,
                interval='1d', nulls='zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                registrations, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                registrations, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    return render(request, 'ci/health_registrations.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def dashboard(request, dashboard_id):
    dashboard = ciApi.get_dashboard(int(dashboard_id))
    context = {"dashboard": dashboard}
    return render(request, 'ci/dashboard.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def dashboard_metric(request):
    client = MetricsApiClient(
        settings.METRIC_API_URL,
        auth=(settings.METRIC_API_USER, settings.METRIC_API_PASSWORD))
    response = {"objects": []}
    filters = {
        "m": [],
        "start": "",
        "interval": "",
        "nulls": ""
    }

    for k, v in request.GET.lists():
        filters[k] = v

    if filters.get('from') is not None:
        filters['from'] = filters['start']

    results = client.get_metrics(**filters)
    for metric in filters['m']:
        if metric in results:
            response["objects"].append({
                "key": metric, "values": results[metric]})
        else:
            response["objects"].append({
                "key": metric, "values": []})

    return JsonResponse(response)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def denied(request):
    return render(request, 'ci/denied.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def not_found(request):
    return render(request, 'ci/not_found.html')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_IDENTITY_SERVICE'])
def identities(request):
    context = {}
    idApi = IdentityStoreApiClient(
        api_url=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["token"]  # noqa
    )
    if 'address_value' in request.GET:
        form = IdentitySearchForm(request.GET)
        if form.is_valid():
            results = idApi.get_identity_by_address(
                address_type=form.cleaned_data['address_type'],
                address_value=form.cleaned_data['address_value'])['results']
        else:
            results = []
    else:
        form = IdentitySearchForm()
        results = idApi.get_identities()['results']

    identities = utils.get_page_of_iterator(
        results, settings.IDENTITY_LIST_PAGE_SIZE,
        request.GET.get('page')
    )

    context['identities'] = identities
    context['form'] = form
    return render(request, 'ci/identities.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_IDENTITY_SERVICE', 'HUB',
                  'SEED_STAGE_BASED_MESSAGING'])
def identity(request, identity):
    idApi = IdentityStoreApiClient(
        api_url=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["token"]  # noqa
    )
    hubApi = HubApiClient(
        api_url=request.session["user_tokens"]["HUB"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["HUB"]["token"]  # noqa
    )
    sbmApi = StageBasedMessagingApiClient(
        api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
    )
    msApi = MessageSenderApiClient(
        api_url=request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["token"]  # noqa
    )
    messagesets_results = sbmApi.get_messagesets()
    messagesets = {}
    schedules = {}
    choices = []
    for messageset in messagesets_results["results"]:
        messagesets[messageset["id"]] = messageset["short_name"]
        schedules[messageset["id"]] = messageset["default_schedule"]
        choices.append((messageset["id"], messageset["short_name"]))

    results = idApi.get_identity(identity)
    sbm_filter = {
        "identity": identity
    }
    subscriptions = sbmApi.get_subscriptions(params=sbm_filter)

    if request.method == "POST":
        if 'add_subscription' in request.POST:
            form = AddSubscriptionForm(request.POST)

            if results['details'].get('preferred_language'):

                if form.is_valid():
                    subscription = {
                        "active": True,
                        "identity": identity,
                        "completed": False,
                        "lang":
                            results['details'].get('preferred_language'),
                        "messageset": form.cleaned_data['messageset'],
                        "next_sequence_number": 1,
                        "schedule":
                            schedules[form.cleaned_data['messageset']],
                        "process_status": 0,
                    }
                    sbmApi.create_subscription(subscription)

                    messages.add_message(
                        request,
                        messages.INFO,
                        'Successfully created a subscription.',
                        extra_tags='success'
                    )
            else:
                messages.add_message(
                    request,
                    messages.ERROR,
                    'No preferred language on the identity.',
                    extra_tags='danger'
                )

        elif 'deactivate_subscription' in request.POST:
            form = DeactivateSubscriptionForm(request.POST)

            if form.is_valid():
                data = {
                    "active": False
                }
                sbmApi.update_subscription(
                    form.cleaned_data['subscription_id'], data)

                messages.add_message(
                    request,
                    messages.INFO,
                    'Successfully deactivated the subscription.',
                    extra_tags='success'
                )

        elif 'optout_identity' in request.POST:
            try:
                details = results.get('details', {})
                addresses = details.get('addresses', {})

                for address_type, addresses in addresses.items():
                    for address, info in addresses.items():
                        idApi.create_optout({
                            "identity": identity,
                            "optout_type": "stop",
                            "address_type": address_type,
                            "address": address,
                            "request_source": "ci"})

                hubApi.create_optout_admin({
                    settings.IDENTITY_FIELD: identity
                })

                messages.add_message(
                    request,
                    messages.INFO,
                    'Successfully opted out.',
                    extra_tags='success'
                )
            except:
                messages.add_message(
                    request,
                    messages.ERROR,
                    'Optout failed.',
                    extra_tags='danger'
                )

    hub_filter = {
        settings.IDENTITY_FIELD: identity
    }
    registrations = hubApi.get_registrations(params=hub_filter)
    changes = hubApi.get_changes(params=hub_filter)
    if results is None:
        return redirect('not_found')

    outbound_message_params = {
        'to_identity': identity,
        'ordering': '-created_at',
    }
    outbound_messages = msApi.get_outbounds(params=outbound_message_params)
    outbound_page = request.GET.get('outbound_page')
    outbound_paginator = Paginator(
        list(outbound_messages['results']),
        settings.IDENTITY_MESSAGES_PAGE_SIZE)

    try:
        outbound_messages = outbound_paginator.page(outbound_page)
    except PageNotAnInteger:
        outbound_messages = outbound_paginator.page(1)
    except EmptyPage:
        outbound_messages = outbound_paginator.page(
            outbound_paginator.num_pages)

    inbound_message_params = {
        'from_identity': identity,
        'ordering': '-created_at',
    }
    inbound_messages = msApi.get_inbounds(inbound_message_params)
    inbound_page = request.GET.get('inbound_page')
    inbound_paginator = Paginator(
        list(inbound_messages['results']),
        settings.IDENTITY_MESSAGES_PAGE_SIZE)

    try:
        inbound_messages = inbound_paginator.page(inbound_page)
    except PageNotAnInteger:
        inbound_messages = inbound_paginator.page(1)
    except EmptyPage:
        inbound_messages = inbound_paginator.page(inbound_paginator.num_pages)

    deactivate_subscription_form = DeactivateSubscriptionForm()
    add_subscription_form = AddSubscriptionForm()
    add_subscription_form.fields['messageset'] = forms.ChoiceField(
                                                    choices=choices)

    optout_visible = False
    details = results.get('details', {})
    addresses = details.get('addresses', {})
    msisdns = addresses.get('msisdn', {})
    optout_visible = any(
        (not d.get('optedout') for _, d in msisdns.items()))

    context = {
        "identity": results,
        "registrations": registrations,
        "changes": changes,
        "messagesets": messagesets,
        "subscriptions": subscriptions,
        "outbound_messages": outbound_messages,
        "add_subscription_form": add_subscription_form,
        "deactivate_subscription_form": deactivate_subscription_form,
        "inbound_messages": inbound_messages,
        "optout_visible": optout_visible
    }
    context.update(csrf(request))
    return render(request, 'ci/identities_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['HUB'])
def registrations(request):
    context = {}
    hubApi = HubApiClient(
        api_url=request.session["user_tokens"]["HUB"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["HUB"]["token"]  # noqa
    )
    if 'mother_id' in request.GET:
        form = RegistrationFilterForm(request.GET)
        if form.is_valid():
            reg_filter = {
                settings.STAGE_FIELD: form.cleaned_data['stage'],
                "validated": form.cleaned_data['validated'],
                settings.IDENTITY_FIELD:
                    form.cleaned_data['mother_id']
            }
            registrations = hubApi.get_registrations(
                params=reg_filter)['results']
        else:
            registrations = []
    else:
        form = RegistrationFilterForm()
        registrations = hubApi.get_registrations()['results']

    context['form'] = form
    context['registrations'] = utils.get_page_of_iterator(
        registrations,
        settings.REGISTRATION_LIST_PAGE_SIZE,
        request.GET.get('page')
    )

    return render(request, 'ci/registrations.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['HUB'])
def registration(request, registration):
    hubApi = HubApiClient(
        api_url=request.session["user_tokens"]["HUB"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["HUB"]["token"]  # noqa
    )
    if request.method == "POST":
        pass
    else:
        results = hubApi.get_registration(registration)
        if results is None:
            return redirect('not_found')
    context = {
        "registration": results
    }
    context.update(csrf(request))
    return render(request, 'ci/registrations_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['HUB'])
def changes(request):
    hubApi = HubApiClient(
        api_url=request.session["user_tokens"]["HUB"]["url"],
        auth_token=request.session["user_tokens"]["HUB"]["token"]
    )
    if 'mother_id' in request.GET:
        form = ChangeFilterForm(request.GET)
        if form.is_valid():
            change_filter = {
                "action": form.cleaned_data['action'],
                "validated": form.cleaned_data['validated'],
                settings.IDENTITY_FIELD:
                    form.cleaned_data['mother_id']
            }
            changes = hubApi.get_changes(params=change_filter)['results']
        else:
            changes = []
    else:
        form = ChangeFilterForm()
        changes = hubApi.get_changes()['results']

    changes = utils.get_page_of_iterator(
        changes, settings.CHANGE_LIST_PAGE_SIZE, request.GET.get('page'))

    context = {
        "changes": changes,
        "form": form
    }
    return render(request, 'ci/changes.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['HUB'])
def change(request, change):
    hubApi = HubApiClient(
        api_url=request.session["user_tokens"]["HUB"]["url"],
        auth_token=request.session["user_tokens"]["HUB"]["token"]
    )
    if request.method == "POST":
        pass
    else:
        results = hubApi.get_change(change)
        if results is None:
            return redirect('not_found')
    context = {"change": results}
    context.update(csrf(request))
    return render(request, 'ci/changes_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_STAGE_BASED_MESSAGING'])
def subscriptions(request):
    sbmApi = StageBasedMessagingApiClient(
        api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
    )

    messagesets_results = sbmApi.get_messagesets()
    messagesets = {}
    for messageset in messagesets_results["results"]:
        messagesets[messageset["id"]] = messageset["short_name"]

    if 'identity' in request.GET:
        form = SubscriptionFilterForm(request.GET)
        if form.is_valid():
            sbm_filter = {
                "identity": form.cleaned_data['identity'],
                "active": form.cleaned_data['active'],
                "completed": form.cleaned_data['completed']
            }
            subscriptions = sbmApi.get_subscriptions(
                params=sbm_filter)['results']
        else:
            subscriptions = []
    else:
        form = SubscriptionFilterForm()
        subscriptions = sbmApi.get_subscriptions()['results']

    subscriptions = utils.get_page_of_iterator(
        subscriptions, settings.SUBSCRIPTION_LIST_PAGE_SIZE,
        request.GET.get('page'))

    context = {
        "subscriptions": subscriptions,
        "messagesets": messagesets,
        "form": form
    }
    context.update(csrf(request))
    return render(request, 'ci/subscriptions.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_STAGE_BASED_MESSAGING'])
def subscription(request, subscription):
    sbmApi = StageBasedMessagingApiClient(
        api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
    )
    messagesets_results = sbmApi.get_messagesets()
    messagesets = {}
    for messageset in messagesets_results["results"]:
        messagesets[messageset["id"]] = messageset["short_name"]

    results = sbmApi.get_subscription(subscription)
    if results is None:
        return redirect('not_found')

    if request.method == "POST":
        try:
            form = ChangeSubscriptionForm(request.POST)
            if form.is_valid():

                lang = form.cleaned_data["language"]
                messageset = form.cleaned_data["messageset"]

                if (lang != results["lang"] or
                        messageset != results["messageset"]):
                    hubApi = HubApiClient(
                        request.session["user_tokens"]["HUB"]["token"],
                        api_url=request.session["user_tokens"]["HUB"]["url"])  # noqa

                    change = {
                        settings.IDENTITY_FIELD: results["identity"],
                        "subscription": subscription
                    }

                    if lang != results["lang"]:
                        change["language"] = lang
                    if messageset != results["messageset"]:
                        change["messageset"] = messagesets[messageset]

                    hubApi.create_change_admin(change)

                    messages.add_message(
                        request,
                        messages.INFO,
                        'Successfully added change.',
                        extra_tags='success'
                    )
        except:
            messages.add_message(
                request,
                messages.ERROR,
                'Change failed.',
                extra_tags='danger'
            )

    languages = sbmApi.get_messageset_languages()

    context = {
        "subscription": results,
        "messagesets": messagesets,
        "languages": json.dumps(languages)
    }
    context.update(csrf(request))
    return render(request, 'ci/subscriptions_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def services(request):
    services = ciApi.get_services()
    context = {"services": services}
    return render(request, 'ci/services.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def service(request, service):
    results = ciApi.get_service(service)
    service_status = ciApi.get_service_status(service)
    context = {
        "service": results,
        "service_status": service_status
    }
    return render(request, 'ci/services_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_STAGE_BASED_MESSAGING'])
def subscription_failures(request):
    sbmApi = StageBasedMessagingApiClient(
        api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
    )
    if request.method == "POST":
        requeue = sbmApi.requeue_failed_tasks()
        if ('requeued_failed_tasks' in requeue and
                requeue['requeued_failed_tasks']):
            messages.add_message(
                request,
                messages.INFO,
                'Successfully re-queued all subscription tasks'
            )
        else:
            messages.add_message(
                request,
                messages.ERROR,
                'Could not re-queued all subscription tasks'
            )
    failures = sbmApi.get_failed_tasks()['results']
    failures = utils.get_page_of_iterator(
        failures, settings.FAILURE_LIST_PAGE_SIZE, request.GET.get('page'))
    context = {
        'failures': failures
    }
    context.update(csrf(request))
    return render(request, 'ci/failures_subscriptions.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_SCHEDULER'])
def schedule_failures(request):
    schdApi = SchedulerApiClient(
        request.session["user_tokens"]["SEED_SCHEDULER"]["token"],  # noqa
        api_url=request.session["user_tokens"]["SEED_SCHEDULER"]["url"]  # noqa
    )
    if request.method == "POST":
        requeue = schdApi.requeue_failed_tasks()
        if ('requeued_failed_tasks' in requeue and
                requeue['requeued_failed_tasks']):
            messages.add_message(
                request,
                messages.INFO,
                'Successfully re-queued all scheduler tasks'
            )
        else:
            messages.add_message(
                request,
                messages.ERROR,
                'Could not re-queued all scheduler tasks'
            )
    failures = schdApi.get_failed_tasks()['results']
    failures = utils.get_page_of_iterator(
        failures, settings.FAILURE_LIST_PAGE_SIZE, request.GET.get('page'))
    context = {
        'failures': failures,
    }
    context.update(csrf(request))
    return render(request, 'ci/failures_schedules.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['SEED_MESSAGE_SENDER'])
def outbound_failures(request):
    msApi = MessageSenderApiClient(
        request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["token"],  # noqa
        api_url=request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["url"]  # noqa
    )
    if request.method == "POST":
        requeue = msApi.requeue_failed_tasks()
        if ('requeued_failed_tasks' in requeue and
                requeue['requeued_failed_tasks']):
            messages.add_message(
                request,
                messages.INFO,
                'Successfully re-queued all outbound tasks'
            )
        else:
            messages.add_message(
                request,
                messages.ERROR,
                'Could not re-queued all outbound tasks'
            )
    failures = msApi.get_failed_tasks()['results']
    failures = utils.get_page_of_iterator(
        failures, settings.FAILURE_LIST_PAGE_SIZE, request.GET.get('page'))
    context = {
        'failures': failures
    }
    context.update(csrf(request))
    return render(request, 'ci/failures_outbounds.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
@tokens_required(['HUB'])
def report_generation(request):
    hubApi = HubApiClient(
        request.session["user_tokens"]["HUB"]["token"],
        api_url=request.session["user_tokens"]["HUB"]["url"])

    if request.method == "POST":
        report_type = request.POST['report_type']
        if report_type == 'registration':
            reg_form = ReportGenerationForm(
                request.POST, auto_id='registration_%s')
            posted_form = reg_form
            msisdn_form = MsisdnReportGenerationForm(auto_id='cohort_%s')
        elif report_type == 'cohort':
            msisdn_form = MsisdnReportGenerationForm(
                request.POST, request.FILES, auto_id='cohort_%s')
            posted_form = msisdn_form
            reg_form = ReportGenerationForm(auto_id='registration_%s')

        if posted_form.is_valid():
            # Remove fields that weren't supplied
            if posted_form.cleaned_data.get('start_date') is None:
                del posted_form.cleaned_data['start_date']
            if posted_form.cleaned_data.get('end_date') is None:
                del posted_form.cleaned_data['end_date']
            if posted_form.cleaned_data.get('email_to') == []:
                del posted_form.cleaned_data['email_to']
            if posted_form.cleaned_data.get('email_from') == "":
                del posted_form.cleaned_data['email_from']
            if posted_form.cleaned_data.get('email_subject') == "":
                del posted_form.cleaned_data['email_subject']

            try:
                results = hubApi.trigger_report_generation(
                        posted_form.cleaned_data)
            except HTTPServiceError as e:
                logger.error('Report generation failed: %s' % e.details)
                messages.add_message(
                    request,
                    messages.ERROR,
                    'Could not start report generation'
                )
            else:
                if 'report_generation_requested' in results:
                    messages.add_message(
                        request,
                        messages.INFO,
                        'Successfully started report generation'
                    )
                else:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        'Could not start report generation'
                    )
    else:
        reg_form = ReportGenerationForm(auto_id='registration_%s')
        msisdn_form = MsisdnReportGenerationForm(auto_id='cohort_%s')
        report_type = ""

    report_tasks = hubApi.get_report_tasks()

    context = {
        "forms": {"registration_form": reg_form, "cohort_form": msisdn_form},
        "report_tasks": report_tasks,
        "report_type": report_type
    }
    context.update(csrf(request))
    return render(request, 'ci/reports.html', context)
