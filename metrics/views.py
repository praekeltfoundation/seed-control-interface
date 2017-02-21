import logging

from django.http import JsonResponse, Http404
from django.conf import settings
from go_http.metrics import MetricsApiClient

from ci.utils import login_required, permission_required
from . import models


logger = logging.getLogger(__name__)


# @login_required(login_url='/login/')
# @permission_required(permission='ci:view', login_url='/login/')
def fetch_metric(request):
    metric_client = MetricsApiClient(
        settings.METRIC_API_TOKEN,
        settings.METRIC_API_URL
    )
    metric = request.GET.get('metric', None)
    kind = request.GET.get('kind', 'month')
    date = request.GET.get('date', None)
    interval = request.GET.get('interval', None)

    if metric is None:
        raise Http404

    date_range = models.DateRange.from_string(date, kind)
    if interval is not None:
        date_range = date_range + int(interval)
    series = models.Series(
        key=metric,
        date_range=date_range,
        metric=metric,
        metric_client=metric_client,
        kind=kind
    )
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
