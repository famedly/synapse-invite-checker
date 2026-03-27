# Copyright (C) 2026 Famedly
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
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from synapse.api.constants import EventTypes, JoinRules
from synapse.api.errors import SynapseError
from synapse.module_api import NOT_SPAM
from synapse.server import HomeServer
from synapse.util.clock import Clock
from twisted.internet import defer
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.invite_checker import EPA_COMMUNICATION_DISABLED_MSG
from tests.base import FederatingModuleApiTestCase
from tests.test_utils import (
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
)


class DisableEpaCommunicationInviteTest(FederatingModuleApiTestCase):
    """
    Tests for the 'disable_epa_communication' config flag on a PRO server.

    When enabled, invites to and from ePA (insurance) domains are blocked with an
    error message.
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.pro_user_a = self.register_user("a", "password")
        self.pro_user_b = self.register_user("b", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update(
            {
                "tim-type": "pro",
                "disable_epa_communication": True,
                "default_permissions": {"defaultSetting": "allow all"},
            }
        )
        return conf

    def may_invite(self, inviter: str, invitee: str, roomid: str):
        req = defer.ensureDeferred(
            self.hs.get_module_api()._callbacks.spam_checker.user_may_invite(
                inviter, invitee, roomid
            )
        )
        self.wait_on_thread(req)
        ret = self.get_success(req)
        if ret == NOT_SPAM:
            return NOT_SPAM
        return ret[0]

    def invite_raises(self, inviter: str, invitee: str, roomid: str) -> SynapseError:
        """Call user_may_invite and expect a SynapseError to be raised."""
        req = defer.ensureDeferred(
            self.hs.get_module_api()._callbacks.spam_checker.user_may_invite(
                inviter, invitee, roomid
            )
        )
        self.wait_on_thread(req)
        return self.failureResultOf(req, SynapseError).value

    def test_invite_from_epa_domain_is_blocked(self) -> None:
        """Invites from an ePA domain must be blocked."""
        epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
        err = self.invite_raises(epa_user, self.pro_user_a, "!madeup:example.com")
        assert err.code == 403
        assert EPA_COMMUNICATION_DISABLED_MSG in err.msg

    def test_invite_to_epa_domain_is_blocked(self) -> None:
        """Invites to an ePA (insurance) domain must be blocked."""
        epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
        err = self.invite_raises(self.pro_user_a, epa_user, "!madeup:example.com")
        assert err.code == 403
        assert EPA_COMMUNICATION_DISABLED_MSG in err.msg

    def test_invite_between_pro_domains_is_allowed(self) -> None:
        """Invites between non-ePA domains must not be affected by the flag."""
        remote_pro_user = f"@bob:{DOMAIN_IN_LIST}"
        assert (
            self.may_invite(remote_pro_user, self.pro_user_a, "!madeup:example.com")
            == NOT_SPAM
        ), "Invite from PRO domain should still be allowed"

    def test_invite_between_local_pro_users_is_allowed(self) -> None:
        """Invites between two local PRO users must not be affected by the flag."""
        assert (
            self.may_invite(self.pro_user_a, self.pro_user_b, "!madeup:example.com")
            == NOT_SPAM
        ), "Invite between local PRO users should still be allowed"


class DisableEpaCommunicationJoinTest(FederatingModuleApiTestCase):
    """
    Tests that user_may_join_room blocks joins when the invite came from an
    ePA domain and disable_epa_communication is enabled.
    """

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.pro_user_a = self.register_user("a", "password")
        self.login("a", "password")

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update(
            {
                "tim-type": "pro",
                "disable_epa_communication": True,
                "default_permissions": {"defaultSetting": "allow all"},
            }
        )
        return conf

    def _make_invite_event_mock(self, sender: str) -> MagicMock:
        """Return a minimal mock invite event for use in user_may_join_room."""
        mock_event = MagicMock()
        mock_event.sender = sender
        mock_event.unsigned = {
            "invite_room_state": [
                {
                    "type": EventTypes.JoinRules,
                    "content": {"join_rule": JoinRules.INVITE},
                    "sender": sender,
                    "state_key": "",
                }
            ]
        }
        return mock_event

    def _patched_store(self, invite_sender: str):
        """Return a context manager that patches the two store calls used in user_may_join_room."""
        mock_room_data = MagicMock()
        mock_room_data.event_id = "$fake_invite_event_id"
        mock_invite_event = self._make_invite_event_mock(invite_sender)

        return (
            patch.object(
                self.hs.get_datastores().main,
                "get_invite_for_local_user_in_room",
                AsyncMock(return_value=mock_room_data),
            ),
            patch.object(
                self.hs.get_datastores().main,
                "get_event",
                AsyncMock(return_value=mock_invite_event),
            ),
        )

    def test_join_invited_by_epa_domain_is_blocked(self) -> None:
        """
        Joining via an invite from an ePA domain must be blocked.
        """
        epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
        room_id = self.create_local_room(self.pro_user_a, [], is_public=False)
        assert room_id is not None

        p_invite, p_event = self._patched_store(epa_user)
        with p_invite, p_event:
            failure = self.get_failure(
                self.inv_checker.user_may_join_room(
                    self.pro_user_a, room_id, is_invited=True
                ),
                SynapseError,
            )
        assert failure.value.code == 403
        assert EPA_COMMUNICATION_DISABLED_MSG in failure.value.msg

    def test_join_invited_by_pro_domain_is_allowed(self) -> None:
        """
        Joining via an invite from a non-ePA domain must not be blocked.
        """
        pro_user = f"@bob:{DOMAIN_IN_LIST}"
        room_id = self.create_local_room(self.pro_user_a, [], is_public=False)
        assert room_id is not None

        p_invite, p_event = self._patched_store(pro_user)
        with p_invite, p_event:
            result = self.get_success(
                self.inv_checker.user_may_join_room(
                    self.pro_user_a, room_id, is_invited=True
                )
            )
        assert result == NOT_SPAM
