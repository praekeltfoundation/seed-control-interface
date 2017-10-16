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


def _get_label_for_key(choices, key):
    for choice_key, label in choices:
        if choice_key == key:
            return label


@register.filter
def get_stage(obj):
    stage = obj.get(settings.STAGE_FIELD)
    return _get_label_for_key(settings.STAGES, stage)


@register.filter
def get_action(obj):
    return _get_label_for_key(settings.ACTIONS, obj.get('action'))
