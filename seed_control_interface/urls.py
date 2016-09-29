import os
from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

admin.site.site_header = os.environ.get('SEED_CONTROL_INTERFACE_TITLE',
                                        'Seed Control Interface Admin')


urlpatterns = patterns(
    '',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^', include('ci.urls')),
)
urlpatterns += staticfiles_urlpatterns()
