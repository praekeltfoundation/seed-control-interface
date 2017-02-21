from django import template


register = template.Library()


@register.inclusion_tag('metrics/chart.html')
def chart_html(chart):
    return {'chart': chart}


@register.inclusion_tag('metrics/chart.js')
def chart_js(chart):
    return {'chart': chart}
