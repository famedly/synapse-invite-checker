# Copyright (C) 2025 Famedly
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
import json
from typing import Any

import yaml
from synapse.api.errors import Codes
from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.types import (
    DefaultPermissionConfig,
    GroupName,
    LOCAL_SERVER_TEMPLATE,
    PermissionConfig,
)
from tests.base import FederatingModuleApiTestCase
from tests.test_utils import INSURANCE_DOMAIN_IN_LIST
from tests.unittest import TestCase


def strip_json_of_whitespace(test_json) -> str:
    """
    Canonicalize the JSON, so any given values are in the same place
    """
    return json.dumps(
        json.loads(test_json),
        # This strips whitespace from around the separators
        separators=(",", ":"),
        # Guarantee all keys are always in the same order
        sort_keys=True,
    )


def assert_test_json_matches_permissions(test_json, permissions) -> None:
    """
    Test assert that stripping all the whitespace and sorting keys of the json yields
    the same json after it has passed through the PermissionConfig
    """
    test_json_stripped = strip_json_of_whitespace(test_json)
    assert test_json_stripped == strip_json_of_whitespace(
        permissions.model_dump_json(exclude_unset=True, exclude_defaults=True)
    )


def assert_test_yaml_matches_json_dump(
    test_yaml: str, dumped_json: dict[str, Any], maybe_server_name: str | None
) -> None:
    """
    Test assert that given test yaml and resultant permissions match how we expect.

    Specifically, it is needed that the root level keys are in place and any sub-keys
    attached match. The data attached to those keys are not relevant as they are not
    used.

    """
    # convert yaml to dict
    converted_yaml: dict[str, Any] = yaml.safe_load(test_yaml)

    # If the local server was included by default with the template, we must account
    # for its existence here. Watch for it to be present, and look for the actual
    # server name in the dumped json
    for key in {
        "defaultSetting",
        "userExceptions",
        "serverExceptions",
        "groupExceptions",
    }:
        yaml_key_found = key in converted_yaml
        dj_key_found = key in dumped_json
        assert yaml_key_found == dj_key_found
        if yaml_key_found:
            for sub_key in converted_yaml[key]:
                if sub_key == LOCAL_SERVER_TEMPLATE:
                    assert maybe_server_name in dumped_json["serverExceptions"]
                    assert LOCAL_SERVER_TEMPLATE not in dumped_json["serverExceptions"]
                else:
                    assert sub_key in dumped_json[key]


class PermissionConfigTest(TestCase):
    @staticmethod
    def test_model_validate_permissions_default() -> None:
        test_json = '{"defaultSetting": "allow all"}'
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_group_excepted(GroupName.isInsuredPerson)

        assert test_permission_object.is_mxid_allowed_to_contact(
            "@bob:example.com", is_mxid_epa=False
        )
        assert_test_json_matches_permissions(test_json, test_permission_object)

        test_json = '{"defaultSetting": "block all"}'
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert not test_permission_object.is_allow_all()
        assert not test_permission_object.is_group_excepted(GroupName.isInsuredPerson)

        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@bob:example.com", is_mxid_epa=False
        )
        assert_test_json_matches_permissions(test_json, test_permission_object)

    def test_model_validate_permissions_complete(self) -> None:
        """
        Test complete forms with both "block all" and "allow all" behaviors. These both
        test with JSON and with a Dict. The both tests are relevant in that the
        PermissionConfig defines additional fields that if unused won't be None, and can
        not be in later JSON used by the account_data system.
        """
        # block all section
        test_json = """
        {
            "defaultSetting": "block all",
            "serverExceptions":
                {
                    "power.rangers": {}
                },
            "groupExceptions":
                [{
                    "groupName": "isInsuredPerson"
                }],
            "userExceptions":
                {
                    "@david:hassel.hoff": {}
                }
        }
        """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)

        assert not test_permission_object.is_allow_all()
        assert test_permission_object.is_group_excepted(GroupName.isInsuredPerson)
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        # TODO: make sure this is right
        assert test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)

        test_dict = {
            "defaultSetting": "block all",
            "serverExceptions": {"power.rangers": {}},
            "groupExceptions": [{"groupName": "isInsuredPerson"}],
            "userExceptions": {"@david:hassel.hoff": {}},
        }

        test_permission_object = PermissionConfig.model_validate(test_dict)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)
        self.assertDictEqual(test_dict, test_permission_object.dump())

        assert not test_permission_object.is_allow_all()
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        # TODO: Make sure this is right
        assert test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )
        assert test_permission_object.is_group_excepted(GroupName.isInsuredPerson)

        # allow all section
        test_json = """
                {
                    "defaultSetting": "allow all",
                    "serverExceptions":
                        {
                            "power.rangers": {}
                        },
                    "groupExceptions":
                        [{
                            "groupName": "isInsuredPerson"
                        }],
                    "userExceptions":
                        {
                            "@david:hassel.hoff": {}
                        }
                }
                """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)

        test_dict = {
            "defaultSetting": "allow all",
            "serverExceptions": {"power.rangers": {}},
            "groupExceptions": [{"groupName": "isInsuredPerson"}],
            "userExceptions": {"@david:hassel.hoff": {}},
        }

        test_permission_object = PermissionConfig.model_validate(test_dict)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)
        self.assertDictEqual(test_dict, test_permission_object.dump())

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )

    def test_model_validate_permissions_scenarios(self) -> None:
        """
        Test both with "block_all" and "allow_all" in various scenarios
        """
        # scenarios
        # 1. a doctor(HBA) has allowed all contact but restricted insured actors
        # 2. an organization user has allowed all contact, but doesn't want to hear from
        #    a pharmacy domain that continuously misreads orders
        # 3. a patient has allowed all, but doesn't want to talk to that weird doctor
        # 4. a doctor has allowed all except insured and forgot he had blocked a specific patient

        # scenario 1
        test_json = """
        {
            "defaultSetting": "allow all",
            "groupExceptions":
                [{
                    "groupName": "isInsuredPerson"
                }]
        }
        """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert test_permission_object.is_allow_all()
        # insured are denied
        assert not test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )
        # everyone else is ok
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)

        # scenario 2
        test_json = """
        {
            "defaultSetting": "allow all",
            "serverExceptions":
                {
                    "pharmacy.com": {}
                }
        }
        """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@needsglasses:pharmacy.com", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@twentytwentyvision:otherpharmacy.com", is_mxid_epa=False
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)

        # scenario 3
        test_json = """
        {
            "defaultSetting": "allow all",
            "userExceptions":
                {
                    "@badbreath:doctors.edu": {}
                }
        }
        """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@badbreath:doctors.edu", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@mothertheresa:doctors.edu", is_mxid_epa=False
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)

        # scenario 4
        test_json = """
        {
            "defaultSetting": "allow all",
            "userExceptions":
                {
                    "@patient:insured.com": {}
                },
            "groupExceptions":
                [{
                    "groupName": "isInsuredPerson"
                }]
        }
        """
        test_permission_object = PermissionConfig.model_validate_json(test_json)

        assert test_permission_object.is_allow_all()
        # Even though this patient permission exists, they are still blocked
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@patient:insured.com", is_mxid_epa=True
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@ghandi:insured.com", is_mxid_epa=True
        )

        assert_test_json_matches_permissions(test_json, test_permission_object)


class DefaultPermissionConfigTest(TestCase):
    """
    This set of cases differs from PermissionConfigTest above in that it has to also
    accommodate the local server name as a template that can be included into the
    serverExceptions section
    """

    server_name = "server_name.com"

    def test_model_validate_permissions_default(self) -> None:
        test_yaml = """
        defaultSetting: allow all
        """
        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.defaultSetting is not None
        assert test_permission_object.defaultSetting == "allow all"

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # Since the mode is "allow all", this will be ignored
        test_permission_object.maybe_update_server_exceptions(self.server_name)
        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        test_yaml = """
        defaultSetting: block all
        """
        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.defaultSetting is not None
        assert test_permission_object.defaultSetting == "block all"

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # Also test that the default of "block all" still tests as expected when
        # the local server template object is missing
        test_permission_object.maybe_update_server_exceptions(self.server_name)
        assert test_permission_object.defaultSetting is not None
        assert test_permission_object.defaultSetting == "block all"

        assert (
            self.server_name not in test_permission_object.serverExceptions
        ), f"No server should be an exception since no {LOCAL_SERVER_TEMPLATE} was included"
        assert isinstance(test_permission_object.groupExceptions, list)

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), self.server_name
        )

        test_yaml = """
        defaultSetting: block all
        serverExceptions:
          "@LOCAL_SERVER@":
        """
        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        # Also test that the default of "block all" still tests as expected when
        # establishing the local server as the exemption
        test_permission_object.maybe_update_server_exceptions(self.server_name)
        assert test_permission_object.defaultSetting is not None
        assert test_permission_object.defaultSetting == "block all"
        assert isinstance(test_permission_object.userExceptions, dict)
        assert isinstance(test_permission_object.serverExceptions, dict)
        assert (
            self.server_name in test_permission_object.serverExceptions
        ), f"server should be an exception since {LOCAL_SERVER_TEMPLATE} was included"
        assert isinstance(test_permission_object.groupExceptions, list)

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), self.server_name
        )

    def test_model_validate_permissions_complete(self) -> None:
        """
        Test complete forms with both "block all" and "allow all" behaviors. These both
        test with JSON and with a Dict. The both tests are relevant in that the
        PermissionConfig defines additional fields that if unused won't be None, and can
        not be in later JSON used by the account_data system.
        """
        # block all section
        test_yaml = """
        defaultSetting: block all
        serverExceptions:
          power.rangers:
        groupExceptions:
        - groupName: isInsuredPerson
        userExceptions:
          "@david:hassel.hoff": {}
        """
        converted_yaml = yaml.safe_load(test_yaml)

        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)

        # Strictly speaking, these methods aren't used by DefaultPermissionConfig, but
        # they came along for the ride so may as well use them
        assert not test_permission_object.is_allow_all()
        assert test_permission_object.is_group_excepted(GroupName.isInsuredPerson)
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # allow all section
        test_yaml = """
            defaultSetting: allow all
            serverExceptions:
              power.rangers:
            groupExceptions:
            - groupName: isInsuredPerson
            userExceptions:
              "@david:hassel.hoff": {}
        """
        converted_yaml = yaml.safe_load(test_yaml)

        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        self.assertIn("power.rangers", test_permission_object.serverExceptions)
        self.assertIn("@david:hassel.hoff", test_permission_object.userExceptions)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@david:hassel.hoff", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )
        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

    def test_model_validate_permissions_scenarios(self) -> None:
        """
        Test both with "block_all" and "allow_all" in various scenarios
        """
        # scenarios
        # 1. a doctor(HBA) has allowed all contact but restricted insured actors
        # 2. an organization user has allowed all contact, but doesn't want to hear from
        #    a pharmacy domain that continuously misreads orders
        # 3. a patient has allowed all, but doesn't want to talk to that weird doctor
        # 4. a doctor has allowed all except insured and forgot he had blocked a
        #    specific patient(which still blocks)

        # scenario 1
        test_yaml = """
        defaultSetting: allow all
        groupExceptions:
        - groupName: isInsuredPerson
        """

        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.is_allow_all()
        # insured are denied
        assert not test_permission_object.is_mxid_allowed_to_contact(
            f"@patient:{INSURANCE_DOMAIN_IN_LIST}", is_mxid_epa=True
        )
        # everyone else is ok
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@billy:power.rangers", is_mxid_epa=False
        )

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # scenario 2
        test_yaml = """
        defaultSetting: allow all
        serverExceptions:
          pharmacy.com:
        """

        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@needsglasses:pharmacy.com", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@twentytwentyvision:otherpharmacy.com", is_mxid_epa=False
        )

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # scenario 3
        test_yaml = """
        defaultSetting: allow all
        userExceptions:
          "@badbreath:doctors.edu":
        """
        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.is_allow_all()
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@badbreath:doctors.edu", is_mxid_epa=False
        )
        assert test_permission_object.is_mxid_allowed_to_contact(
            "@mothertheresa:doctors.edu", is_mxid_epa=False
        )

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )

        # scenario 4
        test_yaml = """
        defaultSetting: allow all
        userExceptions:
          "@patient:insured.com":
        groupExceptions:
        - groupName: isInsuredPerson
        """

        converted_yaml = yaml.safe_load(test_yaml)
        test_permission_object = DefaultPermissionConfig.model_validate(converted_yaml)

        assert test_permission_object.is_allow_all()
        # Even though this patient permission exists, they are still blocked
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@patient:insured.com", is_mxid_epa=True
        )
        assert not test_permission_object.is_mxid_allowed_to_contact(
            "@ghandi:insured.com", is_mxid_epa=True
        )

        assert_test_yaml_matches_json_dump(
            test_yaml, test_permission_object.dump(), None
        )


class LoginGeneratesDefaultPermissionsTestCase(FederatingModuleApiTestCase):
    """
    Test logins generate initial set of permissions for contacting other users
    """

    # This test case does not use any federation features
    # By default, we are SERVER_NAME_FROM_LIST
    # server_name_for_this_server = "tim.test.gematik.de"
    # This test case will model being an PRO server on the federation list

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)

        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        default_perms = {
            "defaultSetting": "allow all",
            "groupExceptions": [{"groupName": "isInsuredPerson"}],
        }
        conf["modules"][0].setdefault("config", {}).update(
            {"default_permissions": default_perms}
        )

        return conf

    def test_login(self) -> None:
        """Test that login will populate the permission structure"""
        # We only pick on user "a" in this test
        config_type = self.get_success(
            self.inv_checker.permissions_handler.get_config_type_from_mxid(self.user_a)
        )
        existing_data = self.get_success(
            self.module_api.account_data_manager.get_global(
                self.user_a, config_type.value
            )
        )

        assert existing_data is None, "Initial permission data should not exist"

        # Login should trigger the initial permission configuration
        self.login("a", "password")

        existing_data = self.get_success(
            self.module_api.account_data_manager.get_global(
                self.user_a, config_type.value
            )
        )
        assert existing_data is not None, "Data should have been populated"

    def test_invite_before_login(self) -> None:
        """
        Test that an invite before user's first login will behave as default
        permissions expect
        """
        # We only pick on user "b" in this test
        config_type = self.get_success(
            self.inv_checker.permissions_handler.get_config_type_from_mxid(self.user_b)
        )
        existing_data = self.get_success(
            self.module_api.account_data_manager.get_global(
                self.user_b, config_type.value
            )
        )

        assert existing_data is None, "Initial permission data should not exist"
        # User "b" has already registered as a user, but never signed in. What happens
        # if an invite comes in that is expected to be denied? Since we set this up as
        # "allow all" but denied insured persons, this should fail
        result = self.get_success_or_raise(
            self.inv_checker.user_may_invite(
                f"@rando-from:{INSURANCE_DOMAIN_IN_LIST}",
                self.user_b,
                f"!example-room:{INSURANCE_DOMAIN_IN_LIST}",
            )
        )
        assert result == Codes.FORBIDDEN, "Invite should have been FORBIDDEN"
