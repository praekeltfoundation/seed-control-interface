from django import template

import seed_control_interface

register = template.Library()


@register.simple_tag
def current_version():
    return seed_control_interface.__version__
