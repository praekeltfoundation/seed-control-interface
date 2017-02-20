from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^(?P<key>[\w-]+)/$', views.fetch_metric, name='fetch_metric'),
]
