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


class RoomScanTaskTestCase(FederatingModuleApiTestCase):
    """
    Test that room scans are done, and subsequent room purges are run
    """

    # This test case will model being an EPA server on the federation list
    remote_pro_user = f"@mxid:{DOMAIN_IN_LIST}"
    remote_pro_user_2 = f"@a:{SERVER_NAME_FROM_LIST}"
    remote_epa_user = f"@alice:{INSURANCE_DOMAIN_IN_LIST}"
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
                }
            }
        )

        return conf

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        self.task_scheduler = self.hs.get_task_scheduler()

        self.user_d = self.register_user("d", "password")
        self.user_d_id = UserID.from_string(self.user_d)
        self.user_e = self.register_user("e", "password")
        self.access_token_d = self.login("d", "password")

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

    def assert_task_status_for_room_is(
        self, room_id: str, task_name: str, status_list: list[TaskStatus] | None = None
    ) -> None:
        """
        Assert that for a given room id, the Statuses listed have a single entry

        If the status_list is empty or None, there should be no tasks to find
        """
        purge_task_list = self.get_success_or_raise(
            self.task_scheduler.get_tasks(actions=[task_name], resource_id=room_id)
        )

        if status_list:
            assert len(purge_task_list) > 0, f"{purge_task_list}"
        else:
            assert len(purge_task_list) == 0, f"{purge_task_list}"

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
        ), f"completed {completed_task}"
        assert len(active_task) == (
            1 if TaskStatus.ACTIVE in status_list else 0
        ), f"active {active_task}"
        assert len(scheduled_task) == (
            1 if TaskStatus.SCHEDULED in status_list else 0
        ), f"scheduled {scheduled_task}"

    @parameterized.expand([("pro_join_and_leave", True), ("pro_never_join", False)])
    def test_room_scan_detects_epa_rooms(
        self, pro_activity: str, pro_join: bool
    ) -> None:
        """
        Test that a room is deleted when a single EPA user and a single PRO user are in
        a room, but the PRO user leaves
        """
        self.add_a_contact_to_user_by_token(self.remote_pro_user, self.access_token_d)

        # Make a room and invite the doctor
        room_id = self.user_d_create_room([self.remote_pro_user], is_public=False)
        assert room_id is not None

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # doctor joins
        if pro_join:
            self.send_join(self.remote_pro_user, room_id)

        # Send a junk hex message into the room, like a sentinel
        self.create_and_send_event(room_id, self.user_d_id)

        # verify there are no tasks associated with this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # doctor leaves room
        if pro_join:
            self.send_leave(self.remote_pro_user, room_id)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # wait for cleanup, should take 6 hours(based on above configuration)
        count = 0
        while True:
            count += 1
            if count == 6:
                break

            # advance() is in seconds, this should be 1 hour
            self.reactor.advance(60 * 60)

            current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
            assert current_rooms is not None

            self.assert_task_status_for_room_is(
                room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
            )

        # Stopped the loop above before advancing the time, so advance() for one more
        # hour, which should allow the task to be scheduled
        self.reactor.advance(60 * 60)

        # Room should still exist
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still exist"

        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [TaskStatus.SCHEDULED]
        )

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(1 * 60)

        # Now the room should be gone
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is None, f"Room should be gone now: {current_rooms}"

        # verify a scheduled task "completed" for this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [TaskStatus.COMPLETE]
        )

    def test_room_scan_ignores_pro_joined_rooms(self) -> None:
        """
        Test that a room is ignored when a single EPA user and a single PRO user are in
        a room, and the EPA user leaves

        As a side note: I don't know what to do about this. Our local user has left the
        room, so it's dangling and won't be cleaned up unless `forget_room_on_leave` is
        turned on. I'm not sure I need to test for this?
        """
        self.add_a_contact_to_user_by_token(self.remote_pro_user, self.access_token_d)

        # Make a room and invite the doctor
        room_id = self.user_d_create_room([self.remote_pro_user], is_public=False)
        assert room_id is not None

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # doctor joins
        self.send_join(self.remote_pro_user, room_id)

        # Send a junk hex message into the room, like a sentinel
        self.create_and_send_event(room_id, self.user_d_id)

        # verify there are no scheduled tasks associated with this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # insured leaves room
        self.helper.leave(room_id, self.user_d, tok=self.access_token_d)

        # TODO: find out if `forget_room_on_leave` is supposed to be configured
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # wait for cleanup, should take 6 hours
        count = 0
        while True:
            count += 1
            if count == 6:
                break
            # advance() is in seconds as a float
            self.reactor.advance(60 * 60)
            current_rooms = self.get_success_or_raise(self.store.get_room(room_id))

            assert current_rooms is not None
            self.assert_task_status_for_room_is(
                room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
            )

        # Stopped the loop above before advancing the time, so advance() for one more
        # hour, which should allow the task to be scheduled
        self.reactor.advance(60 * 60)

        # Room should still exist
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still exist"

        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(1 * 60)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still be around"

        # verify no scheduled tasks were created for this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

    def test_room_scan_detects_only_epa_rooms_with_multiple_hosts(self) -> None:
        """
        Test that a room is not deleted until the last PRO user leaves a room
        """
        self.add_a_contact_to_user_by_token(self.remote_pro_user, self.access_token_d)

        # Make a room and invite the doctor
        room_id = self.user_d_create_room([self.remote_pro_user], is_public=False)
        assert room_id is not None

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # doctor joins
        self.send_join(self.remote_pro_user, room_id)

        # doctor invites another patient, because the first patient isn't allowed
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

        # verify there are no purge tasks associated with this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # doctor 1 leaves room
        self.send_leave(self.remote_pro_user, room_id)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # wait for cleanup, should take 6 hours(based on above configuration)
        count = 0
        while True:
            count += 1
            if count == 6:
                break

            # advance() is in seconds, this should be 1 hour
            self.reactor.advance(60 * 60)

            current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
            assert current_rooms is not None

            self.assert_task_status_for_room_is(
                room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
            )

        # Stopped the loop above before advancing the time, so advance() for one more
        # hour, which should allow the task to be scheduled
        self.reactor.advance(60 * 60)

        # Room should still exist
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still exist"

        # Task was not scheduled, as expected
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(1 * 60)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still be around"

        # verify no scheduled tasks were created for this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
        )

        # doctor 2 leaves
        self.send_leave(self.remote_pro_user_2, room_id)

        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None

        # wait for cleanup, should take 6 hours(based on above configuration)
        count = 0
        while True:
            count += 1
            if count == 6:
                break

            # advance() is in seconds, this should be 1 hour
            self.reactor.advance(60 * 60)

            current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
            assert current_rooms is not None

            self.assert_task_status_for_room_is(
                room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, []
            )

        # Stopped the loop above before advancing the time, so advance() for one more
        # hour, which should allow the task to be scheduled
        self.reactor.advance(60 * 60)

        # Room should still exist
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is not None, "Room should still exist"

        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [TaskStatus.SCHEDULED]
        )

        # The TaskScheduler has a heartbeat of 1 minute, give it that much
        self.reactor.advance(1 * 60)

        # Now the room should be gone
        current_rooms = self.get_success_or_raise(self.store.get_room(room_id))
        assert current_rooms is None, f"Room should be gone now: {current_rooms}"

        # verify a scheduled task "completed" for this room
        self.assert_task_status_for_room_is(
            room_id, SHUTDOWN_AND_PURGE_ROOM_ACTION_NAME, [TaskStatus.COMPLETE]
        )

    def test_scheduling_a_room_delete_is_idempotent(self) -> None:
        # self.hs.mockmod: InviteChecker
        room_id = f"!fake_room_name:{self.server_name_for_this_server}"
        pretest_delete_tasks = self.get_success_or_raise(
            self.hs.mockmod.get_delete_tasks_by_room(room_id)
        )
        assert len(pretest_delete_tasks) == 0

        self.get_success_or_raise(self.hs.mockmod.schedule_room_for_purge(room_id))
        delete_tasks = self.get_success_or_raise(
            self.hs.mockmod.get_delete_tasks_by_room(room_id)
        )
        assert len(delete_tasks) == 1
        delete_task_id = delete_tasks[0].id

        self.get_success_or_raise(self.hs.mockmod.schedule_room_for_purge(room_id))
        second_delete_tasks = self.get_success_or_raise(
            self.hs.mockmod.get_delete_tasks_by_room(room_id)
        )
        assert len(second_delete_tasks) == 1
        second_delete_task_id = second_delete_tasks[0].id
        self.assertEqual(delete_task_id, second_delete_task_id)
