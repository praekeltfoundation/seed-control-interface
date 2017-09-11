from django.conf import settings


def dashboards(request):
    context = {}
    if 'user_dashboards' in request.session:
        context['dashboards'] = request.session['user_dashboards']

    return context


def logo_url(request):
    return {'logo_url': settings.CI_LOGO_URL}
