from django.test import TestCase

from apps.core.models import EnvironmentConfiguration
from apps.api_automation.runner_client import _default_role


class DefaultRoleResolutionTests(TestCase):
    def setUp(self) -> None:
        self.configuration = EnvironmentConfiguration.objects.create(
            name='Default Role Environment',
            environment='default-role',
        )

    def test_marked_authentication_profile_overrides_legacy_variable(self) -> None:
        self.configuration.auth_profiles = {
            'dealer': {'is_default_role': False},
            'customer': {'is_default_role': True},
        }
        self.configuration.variables = {'default_role': 'dealer'}

        self.assertEqual(_default_role(self.configuration), 'customer')

    def test_legacy_variable_is_used_when_no_profile_is_marked(self) -> None:
        self.configuration.auth_profiles = {'dealer': {}, 'customer': {}}
        self.configuration.variables = {'default_role': 'customer'}

        self.assertEqual(_default_role(self.configuration), 'customer')