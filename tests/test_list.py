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
import unittest

import pytest
from pydantic import ValidationError

from synapse_invite_checker.types import FederationList


class FederationListValidationTestCase(unittest.TestCase):
    """
    Test validating the federation list. The schema for such is declared at:
    https://github.com/gematik/api-vzd/blob/main/src/schema/FederationList.json

    """

    def test_federation_list_schema_complete(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "ik": [
                            "012345678"
                        ],
                        "isInsurance": false,
                        "telematikID": "fake_tid",
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        FederationList.model_validate_json(json_str)

    def test_federation_list_schema_missing_domain(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "ik": [
                            "012345678"
                        ],
                        "isInsurance": false,
                        "telematikID": "fake_tid",
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        with pytest.raises(ValidationError):
            FederationList.model_validate_json(json_str)

    def test_federation_list_schema_missing_telematik_id(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "ik": [
                            "012345678"
                        ],
                        "isInsurance": false,
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        with pytest.raises(ValidationError):
            FederationList.model_validate_json(json_str)

    def test_federation_list_schema_missing_tim_anbieter(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "ik": [
                            "012345678"
                        ],
                        "isInsurance": false,
                        "telematikID": "fake_tid"
                    }
                ],
                "version": 0
            }
        """
        FederationList.model_validate_json(json_str)

    def test_federation_list_schema_missing_ik(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "isInsurance": false,
                        "telematikID": "fake_tid",
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        FederationList.model_validate_json(json_str)

    def test_federation_list_schema_empty_ik(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "ik": [],
                        "isInsurance": false,
                        "telematikID": "fake_tid",
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        FederationList.model_validate_json(json_str)

    def test_federation_list_schema_missing_is_insurance(self) -> None:
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "ik": [
                            "012345678"
                        ],
                        "telematikID": "fake_tid",
                        "timAnbieter": "placeholder"
                    }
                ],
                "version": 0
            }
        """
        with pytest.raises(ValidationError):
            FederationList.model_validate_json(json_str)

    def test_federation_list_schema_minimal(self) -> None:
        """
        The Federation List schema declares that only 3 fields are required
        """
        json_str = """
            {
                "domainList": [
                    {
                        "domain": "hs1",
                        "isInsurance": false,
                        "telematikID": "fake_tid"
                    }
                ],
                "version": 0
            }
        """
        FederationList.model_validate_json(json_str)
