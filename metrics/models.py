import attr

from calendar import monthrange
from datetime import timedelta
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta, MO
from django.utils import timezone


def right_pad_list(lst, length, value):
    """Returns a copy of the lst padded to the length specified with the
    given value.
    """
    return lst + [value] * (length - len(lst))


@attr.s
class DateRange(object):
    kind = attr.ib()
    start = attr.ib()
    end = attr.ib()
    interval = attr.ib()

    MONTH = 'month'
    WEEK = 'week'
    DAY = 'day'
    INTERVAL_DAY = '1d'
    INTERVAL_HOUR = '1h'

    def __add__(self, other):
        if not isinstance(other, int):
            msg = "unsupported operand type(s) for +: '{0}' and '{1}'".format(
                self.__class__.__name__,
                type(other).__name__
            )
            raise TypeError(msg)

        if self.kind == self.MONTH:
            kwarg = 'months'
        elif self.kind == self.WEEK:
            kwarg = 'weeks'
        elif self.kind == self.DAY:
            kwarg = 'days'
        new_start = self.start + relativedelta(**{kwarg: other})
        new_end = self.end + relativedelta(**{kwarg: other})
        return attr.assoc(self, start=new_start, end=new_end)

    def __sub__(self, other):
        if not isinstance(other, int):
            msg = "unsupported operand type(s) for -: '{0}' and '{1}'".format(
                self.__class__.__name__,
                type(other).__name__
            )
            raise TypeError(msg)

        if self.kind == self.MONTH:
            kwarg = 'months'
        elif self.kind == self.WEEK:
            kwarg = 'weeks'
        elif self.kind == self.DAY:
            kwarg = 'days'
        new_start = self.start - relativedelta(**{kwarg: other})
        new_end = self.end - relativedelta(**{kwarg: other})
        return attr.assoc(self, start=new_start, end=new_end)

    @property
    def count(self):
        if self.kind == self.MONTH:
            _, count = monthrange(self.start.year, self.start.month)
        elif self.kind == self.WEEK:
            count = 7
        elif self.kind == self.DAY:
            count = 24
        return count

    @property
    def keys(self):
        if self.kind == self.MONTH:
            keys = range(1, self.count + 1)
        elif self.kind == self.WEEK:
            keys = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        elif self.kind == self.DAY:
            keys = range(0, self.count)
        return keys

    @property
    def title(self):
        now = timezone.now()
        if self.kind == self.MONTH:
            if self.start.month == now.month:
                title = 'This Month'
            elif self.start.month == (now.month - 1):
                title = 'Last Month'
            else:
                title = self.start.strftime('%b %Y')
        elif self.kind == self.WEEK:
            title = 'Week of {0}'.format(self.start.date.strftime('%d %b %Y'))
        elif self.kind == self.DAY:
            if self.start.date() == now.date():
                title = 'Today'
            elif self.start.date() == (now.date() - timedelta(days=1)):
                title = 'Yesterday'
            else:
                title = self.start.strftime('%d %b %Y')
        return title

    @classmethod
    def month(cls, dt):
        start = dt.replace(day=1)
        end = start + relativedelta(months=1)
        return cls(
            kind=cls.MONTH,
            start=start,
            end=end,
            interval=cls.INTERVAL_DAY
        )

    @classmethod
    def week(cls, dt):
        # Get last Monday
        start = dt + relativedelta(weekday=MO(-1))
        end = start + relativedelta(weeks=1)
        return cls(
            kind=cls.WEEK,
            start=start,
            end=end,
            interval=cls.INTERVAL_DAY
        )

    @classmethod
    def day(cls, dt):
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + relativedelta(days=1)
        return cls(
            kind=cls.DAY,
            start=start,
            end=end,
            interval=cls.INTERVAL_HOUR
        )

    @classmethod
    def this_month(cls):
        return cls.month(timezone.now())

    @classmethod
    def this_week(cls):
        return cls.week(timezone.now())

    @classmethod
    def today(cls):
        return cls.day(timezone.now())

    @classmethod
    def from_string(cls, date, kind):
        parsed = parse(date)
        if kind == cls.DAY:
            return cls.day(parsed)
        elif kind == cls.WEEK:
            return cls.week(parsed)
        elif kind == cls.MONTH:
            return cls.month(parsed)


@attr.s
class Series(object):
    key = attr.ib()
    date_range = attr.ib()
    metric = attr.ib()
    metric_client = attr.ib()
    kind = attr.ib()
    nulls = attr.ib(default='zeroize')

    BAR = 'bar'
    LINE = 'line'

    def __add__(self, other):
        if not isinstance(other, int):
            msg = "unsupported operand type(s) for +: '{0}' and '{1}'".format(
                self.__class__.__name__,
                type(other).__name__
            )
            raise TypeError(msg)

        return attr.assoc(self, date_range=self.date_range + other)

    def __sub__(self, other):
        if not isinstance(other, int):
            msg = "unsupported operand type(s) for -: '{0}' and '{1}'".format(
                self.__class__.__name__,
                type(other).__name__
            )
            raise TypeError(msg)

        return attr.assoc(self, date_range=self.date_range - other)

    def fetch(self):
        self._metric_data = self.metric_client.get_metric(
            self.metric,
            self.date_range.start.strftime('%Y%m%d'),
            self.date_range.interval,
            self.nulls,
            self.date_range.end.strftime('%Y%m%d')
        )
        self._values = None
        self._keys = None

    @property
    def _data(self):
        if not hasattr(self, '_metric_data') or self._metric_data is None:
            self.fetch()
        return self._metric_data

    def _prepare_values(self):
        data = [point['y'] for point in self._data[self.metric]]
        self._values = right_pad_list(data, self.date_range.count, 0)

    @property
    def values(self):
        if not hasattr(self, '_values') or self._values is None:
            self._prepare_values()
        return self._values

    def _prepare_keys(self):
        self._keys = self.date_range.keys

    @property
    def keys(self):
        if not hasattr(self, '_key') or self._keys is None:
            self._prepare_keys()
        return self._keys

    @property
    def title(self):
        return self.date_range.title


@attr.s
class Chart(object):
    title = attr.ib()
    key = attr.ib()
    data = attr.ib()
    y_axis = attr.ib()
