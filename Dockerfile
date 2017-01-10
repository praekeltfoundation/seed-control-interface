FROM praekeltfoundation/django-bootstrap:onbuild
ENV DJANGO_SETTINGS_MODULE "seed_control_interface.settings"
RUN python manage.py collectstatic --noinput
ENV APP_MODULE "seed_control_interface.wsgi:application"
