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

from synapse_invite_checker.types import (
    GroupName,
    PermissionConfig,
)
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


class PermissionConfigTest(TestCase):
    def test_model_validate_permissions_default(self) -> None:
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
