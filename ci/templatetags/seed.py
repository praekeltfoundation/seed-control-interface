from django import template
from django.conf import settings

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
