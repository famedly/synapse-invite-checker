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
import logging
from http import HTTPStatus
from typing import Any

from synapse.server import HomeServer
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import FederatingModuleApiTestCase
from tests.test_utils import INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL


logger = logging.getLogger(__name__)


class LocalProJoinTestCase(FederatingModuleApiTestCase):
    """
    Tests to verify that we don't break local public/private rooms by accident.
    Specifically, this checks the code for joining a room and not just inviting. This is
    needed for PRO servers as they are allowed to have public rooms. EPA servers do not
    need this test, as they do not allow for local joining.
    """

    # server_name_for_this_server = "tim.test.gematik.de"

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_a = self.login("a", "password")
        self.access_token_b = self.login("b", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "pro"})
        conf["modules"][0].setdefault("config", {}).update(
            {"default_permissions": {"defaultSetting": "allow all"}}
        )
        return conf

    def test_joining_public_with_invites(self) -> None:
        """Test joining a local public room with invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=True)
        assert room_id is not None, "Room should have been created"

        self.helper.invite(room_id, self.user_a, self.user_b, tok=self.access_token_a)
        self.helper.join(room_id, self.user_b, tok=self.access_token_b)

    def test_joining_public_no_invites(self) -> None:
        """Test joining a local public room with no invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=True)
        assert room_id is not None, "Room should have been created"

        self.helper.join(room_id, self.user_b, tok=self.access_token_b)

    def test_joining_private_no_invites(self) -> None:
        """Test joining a local private room with no invites is denied"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.join(
            room_id,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_b,
        )

    def test_joining_private_with_invites(self) -> None:
        """Test joining a local private room with invites is allowed"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.invite(room_id, self.user_a, self.user_b, tok=self.access_token_a)
        self.helper.join(room_id, self.user_b, tok=self.access_token_b)


class LocalEpaJoinTestCase(FederatingModuleApiTestCase):
    """
    Tests to verify that we don't break local public/private rooms behavior by accident.
    Specifically, this checks the code for joining a room and not just inviting
    """

    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.user_a = self.register_user("a", "password")
        self.user_b = self.register_user("b", "password")
        self.access_token_a = self.login("a", "password")
        self.access_token_b = self.login("b", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        conf["modules"][0].setdefault("config", {}).update(
            {"default_permissions": {"defaultSetting": "allow all"}}
        )
        return conf

    def test_joining_public_fails(self) -> None:
        """
        Test joining a local public room with or without invites fails

        See comments below for thoughts on why
        """
        room_id = self.create_local_room(self.user_a, [], is_public=True)
        # Public rooms don't exist, so it should be "None" here. Rather hard to invite
        # and join a room without a room ID
        assert room_id is None, "Room should not have been created"

        # Actually you can invite to a room with no ID, but will still fail for us
        # because invites between two EPA members is forbidden
        self.helper.invite(
            room_id,
            self.user_a,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_a,
        )

        # Trying to join a room with a "None" as a room ID returns a 400(because the
        # "room id" does not start with a "!" as it's supposed to). We don't have to
        # test that

    def test_joining_private_no_invites(self) -> None:
        """Test joining a local private room with no invites is denied"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.join(
            room_id,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_b,
        )

    def test_joining_private_with_invites(self) -> None:
        """Test joining a local private room with invites is denied"""
        room_id = self.create_local_room(self.user_a, [], is_public=False)
        assert room_id is not None, "Room should have been created"

        self.helper.invite(
            room_id,
            self.user_a,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_a,
        )
        self.helper.join(
            room_id,
            self.user_b,
            expect_code=HTTPStatus.FORBIDDEN,
            tok=self.access_token_b,
        )
