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
from dataclasses import dataclass

from synapse_invite_checker.config import InsuredOnlyRoomScanConfig


# This belongs in types.py, but due to circular imports it does not like living there.
# Between DefaultPermissionConfig and InsuredOnlyRoomScanConfig, they are not happy.
# This place is better than sticking it in config.py to make the imports happy
@dataclass(slots=True)
class EpaRoomTimestampResults:
    """
    Collection of timestamps and helpers to decide if a room should have members removed.
    Used for EPA server rooms. Recall that invite/leave timestamps are *only* seeded
    from pro users membership events

    Attributes:
        config: The insured only room scan config section from the invite checker
        last_invite_in_room: The timestamp for the newest 'invite' membership in the
            room. Only used if there was no detected 'leave' event.
        last_leave_in_room: The timestamp of the newest 'leave' membership in the room.
            The preferred timestamp to acquire.
        room_creation_ts: If nothing else, use the room creation as a sentinel. The slim
            possibility exists that no 'leave' event exists and any 'invite' may have
            failed. This is allowed to give a user time to try again before they do not
            have access to this room removed.
    """

    config: InsuredOnlyRoomScanConfig
    last_invite_in_room: int | None = None
    last_leave_in_room: int | None = None
    room_creation_ts: int | None = None

    def should_kick_because_leave(self, time_now: int) -> bool:
        return self.last_leave_in_room is not None and (
            self.last_leave_in_room + self.config.grace_period_ms <= time_now
        )

    def should_kick_because_invite(self, time_now: int) -> bool:
        return self.last_invite_in_room is not None and (
            self.last_invite_in_room + self.config.invite_grace_period_ms <= time_now
        )

    def should_kick_because_creation_event(self, time_now: int) -> bool:
        # For lack of a clearer option, just use the generic grace period here
        return self.room_creation_ts is not None and (
            self.room_creation_ts + self.config.grace_period_ms <= time_now
        )

    def no_appropriate_member_events(self) -> bool:
        return self.last_invite_in_room is None and self.last_leave_in_room is None

    def should_kick_because_no_activity_since_creation(self, time_now: int) -> bool:
        if self.last_invite_in_room is None and self.last_leave_in_room is None:
            return self.should_kick_because_creation_event(time_now)

        # In the unlikely event of there being no invites or leave events, and somehow
        # there is no creation event either, return False so that the room scan skips
        # this room for epa servers. It should still be detected by the room purge scan.
        return False
