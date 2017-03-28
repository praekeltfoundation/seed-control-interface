from django import template

import seed_control_interface

register = template.Library()


@register.simple_tag
def current_version():
    return seed_control_interface.__version__


@register.filter
def cleanup(value):
    return value.replace('_', ' ')


@register.filter
def check_object(value):
    if type(value) == dict:
        return True
    return False
