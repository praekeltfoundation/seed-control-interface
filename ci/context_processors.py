from django.conf import settings


def dashboards(request):
    context = {}
    if 'user_dashboards' in request.session and not settings.HIDE_DASHBOARDS:
        context['dashboards'] = request.session['user_dashboards']

    return context


def hide_health(request):
    return {'hide_health': settings.HIDE_HEALTH}


def hide_dashboards(request):
    return {'hide_dashboards': settings.HIDE_DASHBOARDS}


def show_user_details(request):
    return {'show_user_details': settings.SHOW_USER_DETAILS}


def logo_url(request):
    return {'logo_url': settings.CI_LOGO_URL}
