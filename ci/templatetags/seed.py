from django import template
from django.conf import settings
from django.core.urlresolvers import reverse

import seed_control_interface

import re

register = template.Library()


@register.simple_tag
def current_version():
    return seed_control_interface.__version__


@register.filter
def unslug(value):
    return re.sub('[^0-9a-zA-Z]+', ' ', value).strip()


@register.filter
def is_dict(value):
    return isinstance(value, dict)


@register.filter
def get_identity(obj):
    return obj.get(settings.IDENTITY_FIELD)


@register.inclusion_tag('ci/includes/nav.html', takes_context=True)
def nav_url(context, page, link_text, page_param=None):
    if page_param is not None:
        url = reverse(page, args=[page_param])
    else:
        url = reverse(page)

    if context['request'].path == url:
        html_class = 'active'
    else:
        html_class = ''

    return {
        'class': html_class,
        'link_text': link_text,
        'url': url,
    }
