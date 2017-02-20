import logging
from datetime import timedelta

from django.shortcuts import render, redirect, resolve_url
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.sites.shortcuts import get_current_site
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.utils.http import is_safe_url
from django.utils.timezone import now
from django.http import HttpResponseRedirect, JsonResponse
from django.template.defaulttags import register
from django.template.response import TemplateResponse
from django.core.context_processors import csrf
from django.conf import settings
import dateutil.parser

from seed_services_client.control_interface import ControlInterfaceApiClient
from seed_services_client.identity_store import IdentityStoreApiClient
from seed_services_client.hub import HubApiClient
from seed_services_client.stage_based_messaging \
    import StageBasedMessagingApiClient
from seed_services_client.scheduler import SchedulerApiClient
from seed_services_client.message_sender import MessageSenderApiClient
from go_http.metrics import MetricsApiClient
from .forms import (AuthenticationForm, IdentitySearchForm,
                    RegistrationFilterForm, SubscriptionFilterForm,
                    ChangeFilterForm)
from . import utils
from .utils import login_required, permission_required

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


ciApi = ControlInterfaceApiClient(
    api_url=settings.CONTROL_INTERFACE_SERVICE_URL,
    auth_token=settings.CONTROL_INTERFACE_SERVICE_TOKEN
)


def login(request, template_name='ci/login.html',
          redirect_field_name=REDIRECT_FIELD_NAME,
          authentication_form=AuthenticationForm,
          extra_context=None):
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
            if len(dashboards["results"]) > 0:
                request.session['user_dashboards'] = \
                    dashboards["results"][0]["dashboards"]
                request.session['user_default_dashboard'] = \
                    dashboards["results"][0]["default_dashboard"]["id"]
            else:
                request.session['user_dashboards'] = []
                request.session['user_default_dashboard'] = None

            # Get the user access tokens too and format for easy access
            tokens = ciApi.get_user_service_tokens(
                params={"user_id": user["id"]})
            user_tokens = {}
            if len(tokens["results"]) > 0:
                for token in tokens["results"]:
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
        'logo_url': settings.CI_LOGO_URL
    }
    if extra_context is not None:
        context.update(extra_context)

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


def default_context(session):
    context = {
        "logo_url": settings.CI_LOGO_URL,
        "dashboards": session["user_dashboards"],
    }
    return context


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def index(request):
    if "user_default_dashboard" in request.session and \
            request.session["user_default_dashboard"] is not None:
        return HttpResponseRedirect(reverse('dashboard', args=(
            request.session["user_default_dashboard"],)))
    else:
        context = default_context(request.session)
        return render(request, 'ci/index.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_messages(request):
    if request.is_ajax():
        METRIC_SENT_SUM = 'message.sent.sum'
        client = MetricsApiClient(settings.METRIC_API_TOKEN,
                                  settings.METRIC_API_URL)
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'estimated-vs-sent':
            get_days = today.weekday() + 1
            sent = client.get_metric(METRIC_SENT_SUM, '-%sd' % get_days,
                                     '1d', 'zeroize')
            sent_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='week')

            # The estimate data is stored as .last metrics with 0 - 6
            # representing the days of the week. The cron format specifies
            # 0 = Sunday whereas Python datetime.weekday() specifies
            # 0 = Monday.
            estimate_data = []
            for day in range(7):
                estimated = client.get_metric(
                    'subscriptions.send.estimate.%s.last' % day,
                    '-7d', '1d', 'zeroize')
                estimate_data.append(
                    utils.get_last_value_from_timeseries(estimated))
            return JsonResponse({
                'Estimated': estimate_data,
                'Sent': sent_data
            })

        elif chart_type == 'sent-today':
            get_hours = today.hour
            sent = client.get_metric(METRIC_SENT_SUM, '-%sh' % get_hours,
                                     '1h', 'zeroize')
            sent_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='day')
            return JsonResponse({
                'Today': sent_data
            })

        elif chart_type == 'sent-this-week':
            get_days = today.weekday() + 7  # Include last week in the set.
            sent = client.get_metric(METRIC_SENT_SUM, '-%sd' % get_days,
                                     '1d', 'zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                sent, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                sent, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    context = default_context(request.session)
    return render(request, 'ci/health_messages.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_subscriptions(request):
    if request.is_ajax():
        METRIC_SUBSCRIPTIONS_SUM = 'subscriptions.created.sum'
        client = MetricsApiClient(settings.METRIC_API_TOKEN,
                                  settings.METRIC_API_URL)
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'subscriptions-today':
            get_hours = today.hour + 24  # Include yesterday in the set.
            subscriptions = client.get_metric(
                METRIC_SUBSCRIPTIONS_SUM, '-%sh' % get_hours, '1h', 'zeroize')
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
            subscriptions = client.get_metric(
                METRIC_SUBSCRIPTIONS_SUM, '-%sd' % get_days, '1d', 'zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                subscriptions, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    context = default_context(request.session)
    return render(request, 'ci/health_subscriptions.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def health_registrations(request):
    if request.is_ajax():
        METRIC_REGISTRATIONS_SUM = 'registrations.created.sum'
        client = MetricsApiClient(settings.METRIC_API_TOKEN,
                                  settings.METRIC_API_URL)
        chart_type = request.GET.get('chart_type', None)
        today = now()
        if chart_type == 'registrations-today':
            get_hours = today.hour + 24  # Include yesterday in the set.
            registrations = client.get_metric(
                METRIC_REGISTRATIONS_SUM, '-%sh' % get_hours, '1h', 'zeroize')
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
            registrations = client.get_metric(
                METRIC_REGISTRATIONS_SUM, '-%sd' % get_days, '1d', 'zeroize')
            this_week_data = utils.get_ranged_data_from_timeseries(
                registrations, today, range_type='week')
            last_week_data = utils.get_ranged_data_from_timeseries(
                registrations, today-timedelta(weeks=1), range_type='week')
            return JsonResponse({
                'Last week': last_week_data,
                'This week': this_week_data
            })

    context = default_context(request.session)
    return render(request, 'ci/health_registrations.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def dashboard(request, dashboard_id):
    context = default_context(request.session)
    dashboard = ciApi.get_dashboard(int(dashboard_id))
    context.update({
        "dashboard": dashboard
    })
    return render(request, 'ci/dashboard.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def dashboard_metric(request):
    client = MetricsApiClient(settings.METRIC_API_TOKEN,
                              settings.METRIC_API_URL)
    response = {"objects": []}
    filters = {
        "m": [],
        "start": "",
        "interval": "",
        "nulls": ""
    }

    for k, v in request.GET.lists():
        filters[k] = v

    for metric in filters['m']:
        results = client.get_metric(metric,
                                    filters['start'],
                                    filters['interval'],
                                    filters['nulls'])
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
    context = default_context(request.session)
    return render(request, 'ci/denied.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def not_found(request):
    context = default_context(request.session)
    return render(request, 'ci/not_found.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def identities(request):
    context = default_context(request.session)
    if "SEED_IDENTITY_SERVICE" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
        idApi = IdentityStoreApiClient(
            api_url=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["url"],  # noqa
            auth_token=request.session["user_tokens"]["SEED_IDENTITY_SERVICE"]["token"]  # noqa
        )
        if request.method == "POST":
            form = IdentitySearchForm(request.POST)
            if form.is_valid():
                results = idApi.get_identity_by_address(
                    address_type=form.cleaned_data['address_type'],
                    address_value=form.cleaned_data['address_value'])
            else:
                results = {"count": form.errors}
        else:
            results = idApi.get_identities()
        context.update({
            "identities": results
        })
        context.update(csrf(request))
        return render(request, 'ci/identities.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def identity(request, identity):
    context = default_context(request.session)
    if "SEED_IDENTITY_SERVICE" not in request.session["user_tokens"] and \
            "HUB" not in request.session["user_tokens"] and \
            "SEED_STAGE_BASED_MESSAGING" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
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
        messagesets_results = sbmApi.get_messagesets()
        messagesets = {}
        for messageset in messagesets_results["results"]:
            messagesets[messageset["id"]] = messageset["short_name"]
        if request.method == "POST":
            pass
        else:
            results = idApi.get_identity(identity)
            hub_filter = {
                "mother_id": identity
            }
            registrations = hubApi.get_registrations(params=hub_filter)
            changes = hubApi.get_changes(params=hub_filter)
            sbm_filter = {
                "identity": identity
            }
            subscriptions = sbmApi.get_subscriptions(params=sbm_filter)
            if results is None:
                return redirect('not_found')
        context.update({
            "identity": results,
            "registrations": registrations,
            "changes": changes,
            "messagesets": messagesets,
            "subscriptions": subscriptions
        })
        context.update(csrf(request))
        return render(request, 'ci/identities_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def registrations(request):
    context = default_context(request.session)
    if "HUB" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
        hubApi = HubApiClient(
            api_url=request.session["user_tokens"]["HUB"]["url"],  # noqa
            auth_token=request.session["user_tokens"]["HUB"]["token"]  # noqa
        )
        if request.method == "POST":
            form = RegistrationFilterForm(request.POST)
            if form.is_valid():
                reg_filter = {
                    "stage": form.cleaned_data['stage'],
                    "validated": form.cleaned_data['validated'],
                    "mother_id": form.cleaned_data['mother_id']
                }
                results = hubApi.get_registrations(params=reg_filter)
            else:
                results = {"count": form.errors}
        else:
            form = RegistrationFilterForm()
            results = hubApi.get_registrations()
        context.update({
            "registrations": results,
            "form": form
        })
        context.update(csrf(request))
        return render(request, 'ci/registrations.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def registration(request, registration):
    context = default_context(request.session)
    if "HUB" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
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
        context.update({
            "registration": results
        })
        context.update(csrf(request))
        return render(request, 'ci/registrations_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def changes(request):
    context = default_context(request.session)
    if "HUB" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
        hubApi = HubApiClient(
            api_url=request.session["user_tokens"]["HUB"]["url"],
            auth_token=request.session["user_tokens"]["HUB"]["token"]
        )
        if request.method == "POST":
            form = ChangeFilterForm(request.POST)
            if form.is_valid():
                change_filter = {
                    "action": form.cleaned_data['action'],
                    "validated": form.cleaned_data['validated'],
                    "mother_id": form.cleaned_data['mother_id']
                }
                results = hubApi.get_changes(params=change_filter)
            else:
                results = {"count": form.errors}
        else:
            form = ChangeFilterForm()
            results = hubApi.get_changes()
        context.update({
            "changes": results,
            "form": form
        })
        context.update(csrf(request))
        return render(request, 'ci/changes.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def change(request, change):
    context = default_context(request.session)
    if "HUB" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
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
        context.update({
            "change": results
        })
        context.update(csrf(request))
        return render(request, 'ci/changes_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def subscriptions(request):
    context = default_context(request.session)
    if "SEED_STAGE_BASED_MESSAGING" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
        sbmApi = StageBasedMessagingApiClient(
            api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
            auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
        )
        messagesets_results = sbmApi.get_messagesets()
        messagesets = {}
        for messageset in messagesets_results["results"]:
            messagesets[messageset["id"]] = messageset["short_name"]
        if request.method == "POST":
            form = SubscriptionFilterForm(request.POST)
            if form.is_valid():
                sbm_filter = {
                    "identity": form.cleaned_data['identity'],
                    "active": form.cleaned_data['active'],
                    "completed": form.cleaned_data['completed']
                }
                results = sbmApi.get_subscriptions(params=sbm_filter)
            else:
                results = {"count": form.errors}
        else:
            form = SubscriptionFilterForm()
            results = sbmApi.get_subscriptions()
        context.update({
            "subscriptions": results,
            "messagesets": messagesets,
            "form": form
        })
        context.update(csrf(request))
        return render(request, 'ci/subscriptions.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def subscription(request, subscription):
    context = default_context(request.session)
    if "SEED_STAGE_BASED_MESSAGING" not in request.session["user_tokens"]:
        return redirect('denied')
    else:
        sbmApi = StageBasedMessagingApiClient(
            api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
            auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
        )
        messagesets_results = sbmApi.get_messagesets()
        messagesets = {}
        for messageset in messagesets_results["results"]:
            messagesets[messageset["id"]] = messageset["short_name"]
        if request.method == "POST":
            pass
        else:
            results = sbmApi.get_subscription(subscription)
            if results is None:
                return redirect('not_found')
        context.update({
            "subscription": results,
            "messagesets": messagesets
        })
        context.update(csrf(request))
        return render(request, 'ci/subscriptions_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def services(request):
    context = default_context(request.session)
    services = ciApi.get_services()
    context.update({
        "services": services
    })
    return render(request, 'ci/services.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def service(request, service):
    context = default_context(request.session)
    results = ciApi.get_service(service)
    service_status = ciApi.get_service_status(service)
    context.update({
        "service": results,
        "service_status": service_status
    })
    return render(request, 'ci/services_detail.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def subscription_failures(request):
    context = default_context(request.session)
    if "SEED_STAGE_BASED_MESSAGING" not in request.session["user_tokens"]:
        return redirect('denied')

    sbmApi = StageBasedMessagingApiClient(
        api_url=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["url"],  # noqa
        auth_token=request.session["user_tokens"]["SEED_STAGE_BASED_MESSAGING"]["token"]  # noqa
    )
    results = sbmApi.get_failed_tasks()
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
    context.update({
        'failures': results['results'],
    })
    context.update(csrf(request))
    return render(request, 'ci/failures_subscriptions.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def schedule_failures(request):
    context = default_context(request.session)
    if "SEED_SCHEDULER" not in request.session["user_tokens"]:
        return redirect('denied')

    schdApi = SchedulerApiClient(
        request.session["user_tokens"]["SEED_SCHEDULER"]["token"],  # noqa
        api_url=request.session["user_tokens"]["SEED_SCHEDULER"]["url"]  # noqa
    )
    results = schdApi.get_failed_tasks()
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
    context.update({
        'failures': results,
    })
    context.update(csrf(request))
    return render(request, 'ci/failures_schedules.html', context)


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def outbound_failures(request):
    context = default_context(request.session)
    if "SEED_MESSAGE_SENDER" not in request.session["user_tokens"]:
        return redirect('denied')

    msApi = MessageSenderApiClient(
        request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["token"],  # noqa
        api_url=request.session["user_tokens"]["SEED_MESSAGE_SENDER"]["url"]  # noqa
    )
    results = msApi.get_failed_tasks()
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
    context.update({
        'failures': results['results'],
    })
    context.update(csrf(request))
    return render(request, 'ci/failures_outbounds.html', context)
