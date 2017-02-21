from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^$', views.fetch_metric, name='fetch_metric'),
]
