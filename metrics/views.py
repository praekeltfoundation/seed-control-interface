import logging

from django.http import JsonResponse, Http404
from django.conf import settings
from go_http.metrics import MetricsApiClient

from ci.utils import login_required, permission_required
from . import models


logger = logging.getLogger(__name__)


CONFIGURED_METRICS = {
    'subscriptions-sum': {
        'metric': 'subscriptions.created.sum',
        'kind': models.Series.BAR
    },
}


@login_required(login_url='/login/')
@permission_required(permission='ci:view', login_url='/login/')
def fetch_metric(request, key):
    metric_client = MetricsApiClient(
        settings.METRIC_API_TOKEN,
        settings.METRIC_API_URL
    )
    if key in CONFIGURED_METRICS:
        metric = CONFIGURED_METRICS[key]

        if metric['kind'] == models.Series.MONTH:
            date_range = models.DateRange.this_month()
        elif metric['kind'] == models.Series.WEEK:
            date_range = models.DateRange.this_week()
        elif metric['kind'] == models.Series.DAY:
            date_range = models.DateRange.today()
        series = models.Series(
            key=key,
            date_range=date_range,
            metric=metric['metric'],
            metric_client=metric_client,
            kind=metric['kind']
        )
        time_shift = request.GET.get('ts', None)
        if time_shift is not None:
            time_shift = int(time_shift)
            series = series + time_shift
        resp = {
            'key': series.key,
            'title': series.title,
            'keys': series.keys,
            'values': series.values,
            'kind': series.kind,
            'date_range': {
                'start': series.date_range.start,
                'end': series.date_range.end,
            }
        }
        return JsonResponse(resp)
    else:
        raise Http404
