# Copyright (C) 2020, 2024 Famedly
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
from unittest import TestCase

from synapse.config import ConfigError

from synapse_invite_checker import InviteChecker
from synapse_invite_checker.types import TimType


class ConfigParsingTestCase(TestCase):
    """
    Test that parsing the config can generate Exceptions.

    We start with a basic configuration, and copy it for each test. That is then
    modified to generate the Exceptions.

    An empty string was chosen to represent a 'falsy' value, but removing the
    key has the same effect. May use either interchangeably
    """

    config = {
        "tim-type": "pro",
        "federation_list_url": "https://localhost:8080",
        "federation_localization_url": "https://localhost:8000/localization",
        "federation_list_client_cert": "tests/certs/client.pem",
        "gematik_ca_baseurl": "https://download-ref.tsl.ti-dienste.de/",
    }

    def test_tim_type_is_not_case_sensitive(self) -> None:
        test_config = self.config.copy()
        test_config.update({"tim-type": "ePA"})
        assert InviteChecker.parse_config(test_config).tim_type == TimType.EPA

    def test_tim_type_defaults_to_pro_mode(self) -> None:
        test_config = self.config.copy()
        test_config.pop("tim-type")
        assert InviteChecker.parse_config(test_config).tim_type == TimType.PRO

    def test_incorrect_tim_type_raises(self) -> None:
        test_config = self.config.copy()
        test_config.update({"tim-type": "fake"})
        self.assertRaises(ConfigError, InviteChecker.parse_config, test_config)

    def test_missing_fed_list_or_gematik_ca_url_raises(self) -> None:
        test_config = self.config.copy()
        test_config.update({"federation_list_url": ""})
        self.assertRaises(Exception, InviteChecker.parse_config, test_config)

        test_config = self.config.copy()
        test_config.update({"gematik_ca_baseurl": ""})
        self.assertRaises(Exception, InviteChecker.parse_config, test_config)

    def test_missing_fed_localization_url_raises(self) -> None:
        test_config = self.config.copy()
        test_config.update({"federation_localization_url": ""})
        self.assertRaises(Exception, InviteChecker.parse_config, test_config)

    def test_missing_fed_list_client_certs_raises(self) -> None:
        """
        Test that missing client certs for the Federation List only raises
        if the scheme on the 'federation_list_url' is 'https'
        """
        test_config = self.config.copy()
        test_config.update({"federation_list_client_cert": ""})
        self.assertRaises(Exception, InviteChecker.parse_config, test_config)

    def test_missing_fed_list_client_certs_is_accepted_if_fed_scheme_is_http(
        self,
    ) -> None:
        """
        Both 'federation_list_url' and 'federation_localization_url' must be 'http'
        if Federation List Client certs are missing.

        The schemes matching is a separate test
        """
        test_config = self.config.copy()
        test_config.update(
            {
                "federation_list_client_cert": "",
                "federation_list_url": "http://localhost:8080",
                "federation_localization_url": "http://localhost:8080/localization",
            }
        )

        assert InviteChecker.parse_config(test_config), "Exception maybe?"

    def test_mismatch_scheme_between_fedlist_and_fedloc_raises(self) -> None:
        """Test that one scheme is set to 'http' while another is 'https'"""
        test_config = self.config.copy()
        test_config.update({"federation_list_url": "http://localhost:8080"})

        self.assertRaises(Exception, InviteChecker.parse_config, test_config)

        test_config = self.config.copy()
        test_config.update({"federation_list_url": "https://fake-localhost:8080"})
        self.assertRaises(Exception, InviteChecker.parse_config, test_config)
