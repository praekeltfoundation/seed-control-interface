import time
import attr

from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import resolve_url
from django.utils import timezone
from django.utils.decorators import available_attrs
from django.utils.six.moves.urllib.parse import urlparse


def transform_timeseries_data(timeseries, start, end=None):
    """Transforms a Go Metrics API metric result into a list of
    values for a given window period.

    start and end are expected to be Unix timestamps in microseconds.
    """
    data = []
    include = False
    for metric, points in timeseries.items():
        for point in points:
            if point['x'] == start:
                include = True
            if include:
                data.append(point['y'])
            if end is not None and point['x'] == end:
                return data
    return data


def get_last_value_from_timeseries(timeseries):
    """Gets the most recent non-zero value for a .last metric or zero
    for empty data."""
    if not timeseries:
        return 0
    for metric, points in timeseries.items():
        return next((p['y'] for p in reversed(points) if p['y'] > 0), 0)


def get_timestamp(dt):
    """Returns a Unix timestamp in microseconds for a given datetime."""
    return time.mktime(dt.timetuple()) * 1000


@attr.s
class DTBoundry(object):
    start = attr.ib()
    end = attr.ib()

    @classmethod
    def week_from_datetime(cls, dt):
        """Returns a DTBoundy object with start and end attributes as UTC
        datetime objects that represent the start of the day on Monday and
        Sunday of the given date's week.

        This function will always return the boundries for UTC, not for local
        time.
        """
        # convert localtime to utc
        dt = dt.astimezone(timezone.utc)
        # set it to the earliest possible time in the day
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = dt - timedelta(days=dt.weekday())
        sunday = monday + timedelta(days=6)
        return cls(start=monday, end=sunday)

    @classmethod
    def day_from_datetime(cls, dt):
        """Returns a DTBoundy object with start and end attributes as UTC
        datetime objects that represent the start and end hours of the day
        in the *given datetime's timezone*.

        For example, if given a datetime representing 2017-01-03 in the SAST
        timezone the start and end datetimes returned will be UTC objects
        2 hours before (start="2017-01-02 22:00:00" end="2017-01-03 22:00:00").
        """
        # set datetime to the earliest possible time in the day
        beginning = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        # now convert localtime to utc
        beginning = beginning.astimezone(timezone.utc)
        end = beginning + timedelta(hours=23)
        return cls(start=beginning, end=end)


def right_pad_list(lst, length, value):
    """Returns a copy of the lst padded to the length specified with the
    given value.
    """
    return lst + [value] * (length - len(lst))


def get_ranged_data_from_timeseries(timeseries, dt, range_type='week'):
    if range_type == 'week':
        get_boundry = DTBoundry.week_from_datetime
        padding = 7
    elif range_type == 'day':
        get_boundry = DTBoundry.day_from_datetime
        padding = 24
    else:
        raise ValueError('Invalid value for range_type')

    boundries = get_boundry(dt)
    start = get_timestamp(boundries.start)
    end = get_timestamp(boundries.end)
    sent_data = transform_timeseries_data(timeseries, start, end)
    return right_pad_list(sent_data, length=padding, value=0)


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
