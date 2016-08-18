from django import forms
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from seed_services_client.auth import AuthApiClient
from demands import HTTPServiceError


class AuthenticationForm(forms.Form):
    """
    Base class for authenticating users. Extend this to get a form that accepts
    username/password logins.
    """
    username = forms.CharField(max_length=254, label=_("Email"))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)

    error_messages = {
        'invalid_login': _("Please enter a correct %(username)s and password. "
                           "Note that both fields may be case-sensitive."),
        'inactive': _("This account is inactive."),
    }

    def __init__(self, request=None, *args, **kwargs):
        """
        The 'request' parameter is set for custom auth use by subclasses.
        The form data comes in via the standard 'data' kwarg.
        """
        self.request = request
        self.user_cache = None
        super(AuthenticationForm, self).__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # do remote login
            auth_url = settings.AUTH_SERVICE_URL
            try:
                auth_api = AuthApiClient(username, password, auth_url)
            except HTTPServiceError:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': 'Email'},
                )
            self.user_cache = auth_api.get_permissions()
            self.user_cache["token"] = auth_api.token

        return self.cleaned_data

    def get_user(self):
        return self.user_cache


ADDRESS_TYPES = (
    ("msisdn", "Cell Phone"),
)


class IdentitySearchForm(forms.Form):
    address_value = forms.CharField(widget=forms.TextInput)
    address_type = forms.ChoiceField(
        choices=ADDRESS_TYPES
    )
