import os
from django.conf.urls import include, url
from django.urls import path
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

admin.site.site_header = os.environ.get('SEED_CONTROL_INTERFACE_TITLE',
                                        'Seed Control Interface Admin')


urlpatterns = [
    path('admin/', admin.site.urls),
    url(r'^', include('ci.urls')),
]
urlpatterns += staticfiles_urlpatterns()
