import time
from datetime import timedelta

from django.utils import timezone
from django.utils.six.moves.urllib.parse import urlparse, parse_qs

import attr


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


def extract_query_params(url_str):
    if url_str is None:
        return {}
    return parse_qs(urlparse(url_str).query)
