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
import contextlib
import logging
from typing import Any

from parameterized import parameterized
from synapse.api.constants import Membership
from synapse.api.errors import AuthError
from synapse.handlers.pagination import SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME
from synapse.server import HomeServer
from synapse.types import TaskStatus, UserID
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from tests.base import (
    FederatingModuleApiTestCase,
    construct_extra_content,
)
from tests.test_utils import (
    DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST,
    INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL,
    SERVER_NAME_FROM_LIST,
    event_injection,
)

logger = logging.getLogger(__name__)


class InsuredOnlyRoomScanTaskTestCase(FederatingModuleApiTestCase):
    """
    Test that insured only room scans are done, and subsequent room purges are run
    """

    # This test case will model being an EPA server on the federation list
    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_pro_user_2 = f"@a:{SERVER_NAME_FROM_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    remote_epa_user_2 = f"@bob:{INSURANCE_DOMAIN_IN_LIST}"
    # Our server name
    server_name_for_this_server = INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL
    # The default "fake" remote server name that has its server signing keys auto-injected
    OTHER_SERVER_NAME = DOMAIN_IN_LIST

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "epa"})
        conf["modules"][0].setdefault("config", {}).update(
            {"room_scan_run_interval": "1h"}
        )
        conf["modules"][0].setdefault("config", {}).update(
            {
                "insured_only_room_scan": {
                    "enabled": True,
                    "grace_period": "6h",
                },
                # We aren't testing this here
                "inactive_room_scan": {"enabled": False},
            }
        )
        conf["server_notices"] = {"system_mxid_localpart": "server", "auto_join": True}

        return conf

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.task_scheduler = self.hs.get_task_scheduler()

        self.user_d = self.register_user("d", "password")
        self.user_d_id = UserID.from_string(self.user_d)
        self.user_e = self.register_user("e", "password")
        self.access_token_d = self.login("d", "password")
        self.access_token_e = self.login("e", "password")

        # OTHER_SERVER_NAME already has it's signing key injected into our database so
        # our server doesn't have to make that request. Add the other servers we will be
        # using as well
        self.map_server_name_to_signing_key.update(
            {
                INSURANCE_DOMAIN_IN_LIST: self.inject_servers_signing_key(
                    INSURANCE_DOMAIN_IN_LIST
                ),
                SERVER_NAME_FROM_LIST: self.inject_servers_signing_key(
                    SERVER_NAME_FROM_LIST
                ),
            },
        )

    def user_d_create_room(
        self,
        invitee_list: list[str],
        is_public: bool,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.user_d,
                is_public=is_public,
                tok=self.access_token_d,
                extra_content=construct_extra_content(self.user_d, invitee_list),
            )
        return None

    @parameterized.expand([("pro_join_and_leave", True), ("pro_never_join", False)])
    def test_room_scan_detects_epa_rooms(
        self, pro_activity: str, pro_join: bool
    ) -> None:
        """
        Test that a room is deleted when a single EPA user and a single PRO user are in
        a room, but the PRO user leaves. Also test the same scenario, but if the PRO user
        never joined/left to test that 'maybe broken' rooms are detected
        """
        # Make a room and invite the doctor
        room_id = self.user_d_create_room([self.remote_pro_user], is_public=False)
        assert room_id is not None, "Room should be created"

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        # Needs to be either None or False
        assert not is_room_blocked, "Room should not be blocked yet(try 1)"

        # doctor joins
        if pro_join:
            self.send_join(self.remote_pro_user, room_id)

        # Send a junk hex message into the room, like a sentinel
        self.create_and_send_event(room_id, self.user_d_id)

        # doctor leaves room
        if pro_join:
            self.send_leave(self.remote_pro_user, room_id)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 2)"

        self.reactor.advance(5 * 60 * 60)

        # Room should still exist
        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 3)"

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(60 * 60)

        # Now the room should be gone
        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert is_room_blocked, "Room should be blocked now(try 4)"

        # Send a junk hex message into the room, like a sentinel
        # Inside EventCreationHandler.handle_new_client_event(), this raises as an
        # AuthError(which is a subclass of SynapseError). It appears to be annotated with a 403 as well
        with self.assertRaises(AuthError):
            self.create_and_send_event(room_id, self.user_d_id)

    def test_room_scan_ignores_server_notices_rooms(self) -> None:
        """
        Test that a room is ignored when it is a server notices room
        """
        event_base = self.get_success_or_raise(
            self.hs.get_server_notices_manager().send_notice(
                self.user_d, {"body": "Server Notice message", "msgtype": "m.text"}
            )
        )
        room_id = event_base.room_id
        # Retrieving the room_id is a sign that the room was created, the user was
        # invited, and the message was sent
        assert room_id, "Server notices room should have been found"

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        # Needs to be either None or False
        assert not is_room_blocked, "Room should not be blocked yet(try 1)"

        self.reactor.advance(5 * 60 * 60)

        # Room should still exist
        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 3)"

        # One more hour should be the 6 hours from settings
        self.reactor.advance(60 * 60)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should still exist"

        # Message should succeed, showing the room has not yet been left
        self.get_success_or_raise(
            self.hs.get_server_notices_manager().send_notice(
                self.user_d, {"body": "Server Notice message #2", "msgtype": "m.text"}
            )
        )

    def test_room_scan_detects_only_epa_rooms_with_multiple_hosts(self) -> None:
        """
        Test that a room is not deleted until the last PRO user leaves a room
        """
        # Make a room and invite the doctor
        room_id = self.user_d_create_room([self.remote_pro_user], is_public=False)
        assert room_id is not None

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        # Needs to be either None or False
        assert not is_room_blocked, "Room should not be blocked yet(try 1)"

        # doctor joins
        self.send_join(self.remote_pro_user, room_id)

        # doctor invites 2 more patients, because the first patient isn't allowed. One
        # is remote and the other is from this EPA server
        self.get_success_or_raise(
            event_injection.inject_member_event(
                self.hs,
                room_id,
                self.remote_pro_user,
                Membership.INVITE,
                target=self.remote_epa_user,
            )
        )

        # other patient joins
        self.send_join(self.remote_epa_user, room_id)

        self.get_success_or_raise(
            event_injection.inject_member_event(
                self.hs,
                room_id,
                self.remote_pro_user,
                Membership.INVITE,
                target=self.user_e,
            )
        )

        self.helper.join(room_id, self.user_e, tok=self.access_token_e)

        # doctor invites another doctor
        self.get_success_or_raise(
            event_injection.inject_member_event(
                self.hs,
                room_id,
                self.remote_pro_user,
                Membership.INVITE,
                target=self.remote_pro_user_2,
            )
        )

        # other doctor joins
        self.send_join(self.remote_pro_user_2, room_id)

        # Send a junk hex message into the room, like a sentinel
        self.create_and_send_event(room_id, self.user_d_id)

        # They all just found out a friend of the remote patient may have more info
        self.get_success_or_raise(
            event_injection.inject_member_event(
                self.hs,
                room_id,
                self.remote_pro_user,
                Membership.INVITE,
                target=self.remote_epa_user_2,
            )
        )

        # other patient joins
        self.send_join(self.remote_epa_user_2, room_id)

        # Original patient says "thanks you can go now"
        self.create_and_send_event(room_id, self.user_d_id)

        # friend of friend of patient leaves
        self.send_leave(self.remote_epa_user_2, room_id)

        # doctor 1 leaves room
        self.send_leave(self.remote_pro_user, room_id)

        # The other local insured leaves the room
        self.helper.leave(room_id, self.user_e, tok=self.access_token_e)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 2)"

        self.reactor.advance(5 * 60 * 60)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 3)"

        # Normally, this would trigger the auto-kicker. But the doctor hasn't left yet
        self.reactor.advance(60 * 60)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 4)"

        # doctor 2 leaves
        self.send_leave(self.remote_pro_user_2, room_id)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 5)"

        self.reactor.advance(5 * 60 * 60)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert not is_room_blocked, "Room should not be blocked yet(try 6)"

        # One more hour should be the 6 hours from settings
        self.reactor.advance(60 * 60)

        is_room_blocked = self.get_success_or_raise(self.store.is_room_blocked(room_id))
        assert is_room_blocked, "Room should be blocked now"

        # Inside EventCreationHandler.handle_new_client_event(), this raises as an
        # AuthError(which is a subclass of SynapseError). It appears to be annotated with a 403 as well
        with self.assertRaises(AuthError):
            self.create_and_send_event(room_id, self.user_d_id)


class InactiveRoomScanTaskTestCase(FederatingModuleApiTestCase):
    """
    Test that inactive room scans are done, and subsequent room purges are run
    """

    # This test case will model being an PRO server on the federation list
    # By default we are SERVER_NAME_FROM_LIST

    # Test with one other remote PRO server and one EPA server
    # The inactive grace period is going to be 6 hours, room scans run each hour
    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
    # The default "fake" remote server name that has its server signing keys auto-injected
    OTHER_SERVER_NAME = DOMAIN_IN_LIST

    def default_config(self) -> dict[str, Any]:
        conf = super().default_config()
        assert "modules" in conf, "modules missing from config dict during construction"

        # There should only be a single item in the 'modules' list, since this tests that module
        assert len(conf["modules"]) == 1, "more than one module found in config"

        conf["modules"][0].setdefault("config", {}).update({"tim-type": "pro"})
        conf["modules"][0].setdefault("config", {}).update(
            {"room_scan_run_interval": "1h"}
        )
        conf["modules"][0].setdefault("config", {}).update(
            {
                "inactive_room_scan": {
                    "enabled": True,
                    "grace_period": "6h",
                }
            }
        )

        return conf

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.task_scheduler = self.hs.get_task_scheduler()

        self.user_a = self.register_user("a", "password")
        self.user_a_id = UserID.from_string(self.user_a)
        self.access_token_a = self.login("a", "password")
        self.user_b = self.register_user("b", "password")
        self.user_b_id = UserID.from_string(self.user_b)
        self.access_token_b = self.login("b", "password")
        self.user_c = self.register_user("c", "password")
        self.user_c_id = UserID.from_string(self.user_c)
        self.access_token_c = self.login("c", "password")

        # OTHER_SERVER_NAME already has it's signing key injected into our database so
        # our server doesn't have to make that request. Add the other servers we will be
        # using as well
        self.map_server_name_to_signing_key.update(
            {
                INSURANCE_DOMAIN_IN_LIST: self.inject_servers_signing_key(
                    INSURANCE_DOMAIN_IN_LIST
                ),
            },
        )
        self.map_user_name_to_tokens = {
            self.user_a: self.access_token_a,
            self.user_b: self.access_token_b,
            self.user_c: self.access_token_c,
        }

    def user_a_create_room(
        self,
        invitee_list: list[str],
        is_public: bool,
    ) -> str | None:
        """
        Helper to send an api request with a full set of required additional room state
        to the room creation matrix endpoint.
        """
        # Hide the assertion from create_room_as() when the error code is unexpected. It
        # makes errors for the tests less clear when all we get is the http response
        with contextlib.suppress(AssertionError):
            return self.helper.create_room_as(
                self.user_a,
                is_public=is_public,
                tok=self.access_token_a,
                extra_content=construct_extra_content(self.user_a, invitee_list),
            )
        return None

    def opinionated_join(self, room_id: str, user: str) -> None:
        """
        Helper to join a room whether this is a local or remote user
        """
        user_domain = UserID.from_string(user).domain
        if user_domain == self.server_name_for_this_server:
            # local
            self.helper.join(room_id, user, tok=self.map_user_name_to_tokens.get(user))
        else:
            # remote
            self.send_join(user, room_id)

    def assert_task_status_for_room_is(
        self,
        room_id: str,
        task_name: str,
        status_list: list[TaskStatus] | None = None,
        comment: str = "",
    ) -> None:
        """
        Assert that for a given room id, the Statuses listed have a single entry

        If the status_list is empty or None, there should be no tasks to find
        """
        purge_task_list = self.get_success_or_raise(
            self.task_scheduler.get_tasks(actions=[task_name], resource_id=room_id)
        )

        if status_list:
            assert (
                len(purge_task_list) > 0
            ), f"{comment} | GT status_list: {status_list}, purge_list: {purge_task_list}"
        else:
            assert (
                len(purge_task_list) == 0
            ), f"{comment} | EQ status_list: {status_list}, purge_list: {purge_task_list}"

        completed_task = [
            task for task in purge_task_list if task.status == TaskStatus.COMPLETE
        ]
        active_task = [
            task for task in purge_task_list if task.status == TaskStatus.ACTIVE
        ]
        scheduled_task = [
            task for task in purge_task_list if task.status == TaskStatus.SCHEDULED
        ]
        assert len(completed_task) == (
            1 if TaskStatus.COMPLETE in status_list else 0
        ), f"{comment} | completed {completed_task}"
        assert len(active_task) == (
            1 if TaskStatus.ACTIVE in status_list else 0
        ), f"{comment} | active {active_task}"
        assert len(scheduled_task) == (
            1 if TaskStatus.SCHEDULED in status_list else 0
        ), f"{comment} | scheduled {scheduled_task}"

    # test for private dm between two local users
    # test for private dm between a local and remote user
    # test for public room on local server
    # test for basic dm between a local and remote epa user

    # I'm not sure I like the hard coding of the user names here, but can not access
    # "self" to just reference it
    @parameterized.expand(
        [
            # (name to give the test, list of users to test with, is public room, any messages in room?)
            (
                "private_room_2_local_users_with_messages",
                [f"@b:{SERVER_NAME_FROM_LIST}"],
                False,
                True,
            ),
            (
                "private_room_2_local_users_no_messages",
                [f"@b:{SERVER_NAME_FROM_LIST}"],
                False,
                False,
            ),
            (
                "private_room_1_local_user_1_remote_pro_user",
                [f"@mxid:{DOMAIN_IN_LIST}"],
                False,
                True,
            ),
            (
                "public_room_3_local_users",
                [f"@b:{SERVER_NAME_FROM_LIST}", f"@c:{SERVER_NAME_FROM_LIST}"],
                True,
                True,
            ),
            (
                "private_room_with_1_pro_1_epa",
                [f"@b:{SERVER_NAME_FROM_LIST}", f"@alice:{INSURANCE_DOMAIN_IN_LIST}"],
                False,
                True,
            ),
        ]
    )
    def test(
        self, _: str, other_users: list[str], is_public: bool, send_messages: bool
    ) -> None:
        """
        Test that a room is deleted when a local PRO user and various others don't touch
        a room for "inactive_room_scan.grace_period" amount of time
        """
        # Make a room and invite the other occupant(s)
        room_id = self.user_a_create_room([], is_public=is_public)
        assert room_id is not None, "Room should exist"

        for other_user in other_users:
            self.helper.invite(room_id, targ=other_user, tok=self.access_token_a)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should exist from initial get_room()"

        # other user joins
        for other_user in other_users:
            self.opinionated_join(room_id, other_user)

        # Send a junk hex message into the room, this is the message the scan will find
        if send_messages:
            self.create_and_send_event(room_id, self.user_a_id)

        # verify there are no shutdown tasks associated with this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [], "first check"
        )

        # wait for cleanup, should take 6 hours(based on above configuration)
        count = 0
        while True:
            count += 1
            if count == 6:
                break

            # advance() is in seconds, this should be 1 hour
            self.reactor.advance(60 * 60)

            current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
            assert (
                current_rooms is not None
            ), f"Room should still exist at count: {count}"

            self.assert_task_status_for_room_is(
                room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [], f"loop count: {count}"
            )

        # Stopped the loop above before advancing the time, so advance() for one more
        # hour, which should allow the task to be scheduled
        self.reactor.advance(60 * 60)

        # Room should still exist
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still exist after loop finished"

        self.assert_task_status_for_room_is(
            room_id,
            SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME,
            [TaskStatus.SCHEDULED],
            "after loop",
        )

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(1 * 60)

        # Now the room should be gone
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is None, f"Room should be gone now: {current_rooms}"

        # verify a scheduled task "completed" for this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [TaskStatus.COMPLETE], "end"
        )

    def test_scheduling_a_room_delete_is_idempotent(self) -> None:
        room_id = f"!fake_room_name:{self.server_name_for_this_server}"
        pretest_delete_tasks = self.get_success_or_raise(
            self.inv_checker.get_delete_tasks_by_room(room_id)
        )
        assert len(pretest_delete_tasks) == 0

        self.get_success_or_raise(self.inv_checker.schedule_room_for_purge(room_id))
        delete_tasks = self.get_success_or_raise(
            self.inv_checker.get_delete_tasks_by_room(room_id)
        )
        assert len(delete_tasks) == 1
        delete_task_id = delete_tasks[0].id

        self.get_success_or_raise(self.inv_checker.schedule_room_for_purge(room_id))
        second_delete_tasks = self.get_success_or_raise(
            self.inv_checker.get_delete_tasks_by_room(room_id)
        )
        assert len(second_delete_tasks) == 1
        second_delete_task_id = second_delete_tasks[0].id
        self.assertEqual(delete_task_id, second_delete_task_id)
