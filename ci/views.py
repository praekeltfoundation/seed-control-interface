from functools import wraps

from django.shortcuts import render, redirect, resolve_url
from django.utils.decorators import available_attrs
from django.utils.six.moves.urllib.parse import urlparse
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import is_safe_url
from django.http import HttpResponseRedirect
from django.template.defaulttags import register
from django.template.response import TemplateResponse
from django.conf import settings
import dateutil.parser

from seed_services_client.control_interface import ControlInterfaceApiClient
from .forms import AuthenticationForm


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


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_date(date_string):
    if date_string is not None:
        return dateutil.parser.parse(date_string)


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
    if extra_context is not None:
        context.update(extra_context)

    return TemplateResponse(request, template_name, context)


def logout(request):
    try:
        del request.session['user_token']
        del request.session['user_email']
        del request.session['user_permissions']
    except KeyError:
        pass
    return redirect('index')


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def index(request):
    return render(request, 'ci/index.html')
