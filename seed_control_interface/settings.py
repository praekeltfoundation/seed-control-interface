"""
Django settings for seed_control_interface project.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""

import os

import dj_database_url

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'REPLACEME')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', False)

ALLOWED_HOSTS = ['*']

# Application definition

INSTALLED_APPS = (
    # admin
    'django.contrib.admin',
    # core
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 3rd party
    'raven.contrib.django.raven_compat',
    'bootstrapform',
    # us
    'ci',

)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'seed_control_interface.urls'

WSGI_APPLICATION = 'seed_control_interface.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get(
            'SEED_CONTROL_INTERFACE_DATABASE',
            'postgres://postgres:@localhost/seed_control_interface')),
}


# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

LANGUAGE_CODE = 'en-gb'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'django.contrib.staticfiles.finders.FileSystemFinder',
)

STATIC_ROOT = 'staticfiles'
STATIC_URL = '/static/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            # insert your TEMPLATE_DIRS here
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # Insert your TEMPLATE_CONTEXT_PROCESSORS here
                'ci.context_processors.dashboards',
                'ci.context_processors.logo_url',
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'django.core.context_processors.request',
            ],
        },
    },
]

# Sentry configuration
RAVEN_CONFIG = {
    # DevOps will supply you with this.
    'dsn': os.environ.get('SEED_CONTROL_INTERFACE_SENTRY_DSN', None),
}

CONTROL_INTERFACE_SERVICE_URL = os.environ.get(
    'CONTROL_INTERFACE_SERVICE_URL',
    'http://localhost:8003/api/v1')

CONTROL_INTERFACE_SERVICE_TOKEN = os.environ.get(
    'CONTROL_INTERFACE_SERVICE_TOKEN',
    'REPLACEME')

METRIC_API_URL = os.environ.get(
    'METRIC_API_URL',
    'http://localhost:8005/api/v1')

METRIC_API_USER = os.environ.get(
    'METRIC_API_USER',
    'REPLACEME')

METRIC_API_PASSWORD = os.environ.get(
    'METRIC_API_PASSWORD',
    'REPLACEME')

AUTH_SERVICE_URL = os.environ.get(
    'AUTH_SERVICE_URL',
    'http://localhost:8000')

CI_LOGO_URL = os.environ.get(
    'CI_LOGO_URL',
    '/static/ci/img/logo.png')

HUB_URL = os.environ.get(
    'HUB_URL', 'http://localhost:8006/api/v1')

HUB_TOKEN = os.environ.get(
    'HUB_TOKEN', 'REPLACEME')

IDENTITY_STORE_URL = os.environ.get(
    'IDENTITY_STORE_URL', 'http://localhost:8007/api/v1')

IDENTITY_STORE_TOKEN = os.environ.get(
    'IDENTITY_STORE_TOKEN', 'REPLACEME')

IDENTITY_FIELD = os.environ.get('IDENTITY_FIELD', 'mother_id')
STAGE_FIELD = os.environ.get('STAGE_FIELD', 'stage')
_stage_string = os.environ.get(
    'STAGES',
    'prebirth:Mother is pregnant,postbirth:Baby has been born,loss:Baby loss')

STAGES = tuple(
    tuple(stage.split(':')) for stage in _stage_string.split(','))

_action_string = os.environ.get(
    'ACTIONS',
    'change_messaging:Change messaging type and/or reception times,'
    'change_loss:Change to loss messaging,'
    'unsubscribe_household_only:Unsubscribe household msg receiver,'
    'unsubscribe_mother_only:Unsubscribe mother from messages,'
    'change_language:Change language,change_baby:Change to baby message'
)

ACTIONS = tuple(
    tuple(action.split(':')) for action in _action_string.split(','))

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_SUBJECT_PREFIX = os.environ.get('EMAIL_SUBJECT_PREFIX', '[Django]')

IDENTITY_MESSAGES_PAGE_SIZE = 30
IDENTITY_LIST_PAGE_SIZE = 30
REGISTRATION_LIST_PAGE_SIZE = 30
CHANGE_LIST_PAGE_SIZE = 30
SUBSCRIPTION_LIST_PAGE_SIZE = 30
FAILURE_LIST_PAGE_SIZE = 30
