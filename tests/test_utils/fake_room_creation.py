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
from typing import Any

from signedjson.types import SigningKey
from synapse.api.constants import (
    EventTypes,
    GuestAccess,
    HistoryVisibility,
    JoinRules,
    Membership,
    RoomCreationPreset,
)
from synapse.api.room_versions import KNOWN_ROOM_VERSIONS, RoomVersion
from synapse.config.homeserver import HomeServerConfig
from synapse.crypto.event_signing import add_hashes_and_signatures
from synapse.events import EventBase, make_event_from_dict
from synapse.federation.federation_client import SendJoinResult
from synapse.types import RoomID
from synapse.util import Clock, stringutils


class FakeRoom:
    """
    This creates enough of a room to allow a remote join to complete processing. Do not
    re-use these rooms like can be done for local rooms: the infrastructure does not
    exist to properly send new information into the room and repeated invites/joins will
    not work.
    """

    room_version: RoomVersion
    room_id: RoomID
    creator_id: str
    depth_counter: int
    auth_events_list: list[EventBase]
    # This is almost the same as forward extremities
    current_prev_events_id_list: list[str]
    # does not include membership events, separate mapping
    map_of_state_events_by_type: dict[EventTypes, EventBase]
    # membership events
    map_of_membership_by_mxid: dict[str, EventBase]

    def __init__(
        self,
        hs_config: HomeServerConfig,
        clock: Clock,
        creator: str,
        other_server_name: str,
        other_server_signing_key: SigningKey,
        room_ver: str | None = None,
        room_preset: str = RoomCreationPreset.PUBLIC_CHAT,
        join_rule_override: str | None = None,
        history_visibility_override: str | None = None,
        guest_access_override: str | None = None,
    ) -> None:
        self.creator_id = creator
        self.clock = clock
        self.server_name_this_room_is_on = other_server_name
        self.signing_key = other_server_signing_key
        self.depth_counter = 0
        # generate a room id
        random_string = stringutils.random_string(18)
        self.room_id = RoomID(random_string, other_server_name)

        if room_ver is None:
            room_ver = hs_config.server.default_room_version.identifier

        self.room_version = KNOWN_ROOM_VERSIONS.get(room_ver)
        # TODO: factor this out into a function that can construct it instead
        self.auth_events_list = []
        self.current_prev_events_id_list = []
        self.map_of_state_events_by_type = {}
        self.map_of_membership_by_mxid = {}

        # sort out the preset or the overrides
        assert room_preset in [
            RoomCreationPreset.PUBLIC_CHAT,
            RoomCreationPreset.PRIVATE_CHAT,
            RoomCreationPreset.TRUSTED_PRIVATE_CHAT,
        ], f"An unknown room creation preset was provided: {room_preset}"
        if room_preset == RoomCreationPreset.PUBLIC_CHAT:
            _join_rule = JoinRules.PUBLIC
            _his_vis = HistoryVisibility.SHARED
            _guest_access = GuestAccess.FORBIDDEN
        elif (
            room_preset == RoomCreationPreset.PRIVATE_CHAT
            or room_preset == RoomCreationPreset.TRUSTED_PRIVATE_CHAT
        ):
            _join_rule = JoinRules.INVITE
            _his_vis = HistoryVisibility.SHARED
            _guest_access = GuestAccess.CAN_JOIN
        else:
            raise ValueError("'room_preset' was an unknown value")

        join_rule = join_rule_override or _join_rule
        history_visibility = history_visibility_override or _his_vis
        guest_access = guest_access_override or _guest_access

        # Build the room
        _create_event = self.create_event()
        _creator_member_event = self.creator_member_event()
        _power_levels_event = self.initial_power_levels_event()
        _join_rules_event = self.initial_join_rules_event(join_rule)
        _history_visibility_event = self.initial_history_visibility_event(
            history_visibility
        )
        _guest_access_event = self.initial_guest_access_event(guest_access)
        # TODO: sort out what other state bits should add

    def create_send_invite_request(
        self,
        sender_user_id: str,
        target_user_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        """
        Create invite signed by the remote server. This will be the content of an
        invite request. This is like a template, but is not added to the state of the
        room until it is returned after being submitted to our test server(see
        `update_member_state`)

        Returns:
            tuple of the pdu json, the room initial state list, and the event ID of that pdu
        """
        # as a member event, this needs the basic set of auth, plus join_rules
        auth_events = [e.event_id for e in self.auth_events_list]
        auth_events.append(
            self.map_of_state_events_by_type[EventTypes.JoinRules].event_id
        )

        event = self._member_event(
            target_user_id,
            Membership.INVITE,
            sender_user_id,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        room_initial_state = []
        for event_type in [EventTypes.Create, EventTypes.JoinRules]:
            room_initial_state.append(
                strip_state_event(
                    self.map_of_state_events_by_type[event_type].get_dict()
                )
            )
        # Save this to the state of the room. Rather it is denied or not by the real
        # server, it is still part of the room to be accounted for. After it is processed
        # by the real server, it should be updated. If it is denied, the room will be
        # always be broken from the standpoint of the real server since at some point
        # the prev_event will resolve back to this
        self.map_of_membership_by_mxid[event.state_key] = event
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return (
            event.get_pdu_json(self.clock.time_msec()),
            room_initial_state,
            event.event_id,
        )

    def promote_member_invite(
        self,
        signed_pdu: dict[str, Any],
    ) -> EventBase:
        """
        This membership event is already part of the room "state", but it needs its
        signatures updated to include the receiving server
        """
        event = make_event_from_dict(
            signed_pdu,
            room_version=self.room_version,
        )

        # Update the state of the room, but do not increment depth. It's not a new
        # event, just one that got signed and returned
        self.map_of_membership_by_mxid[event.state_key] = event
        # self.current_prev_events_id_list = [event.event_id]

        return event

    def create_make_join_response(
        self,
        user_id: str,
    ) -> tuple[str, EventBase, RoomVersion]:
        """
        A helper to construct the response for FederationClient.make_membership_event()
        Args:
            user_id:

        Returns: tuple of [origin_server_domain, join event, RoomVersion]

        """
        # as a member event, this needs the basic set of auth, plus join_rules
        auth_events = [e.event_id for e in self.auth_events_list]
        auth_events.append(
            self.map_of_state_events_by_type[EventTypes.JoinRules].event_id
        )
        # if there was an invite, we'll find it in the membership state
        if user_id in self.map_of_membership_by_mxid:
            invite_event = self.map_of_membership_by_mxid[user_id]
            auth_events.append(invite_event.event_id)

        event = self._member_event(
            user_id,
            Membership.JOIN,
            user_id,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        return self.room_id.domain, event, self.room_version

    def create_send_join_response(
        self,
        user_id: str,
        pdu: dict[str, Any],
    ) -> SendJoinResult:
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        event = make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )

        # The state and auth_chain need to both represent state *before* and not *after*
        # the join itself
        # as a member event, this needs the basic set of auth, plus join_rules
        auth_chain = self.auth_events_list.copy()
        auth_chain.append(self.map_of_state_events_by_type[EventTypes.JoinRules])
        # if there was an invite, we'll find it in the members state
        if user_id in self.map_of_membership_by_mxid:
            invite_event = self.map_of_membership_by_mxid[user_id]
            auth_chain.append(invite_event)

        state = list(self.map_of_state_events_by_type.values())
        state.extend(self.map_of_membership_by_mxid.values())

        # This join is almost complete. Be sure to insert the new event into the current
        # room state before sending it back
        self.map_of_membership_by_mxid[user_id] = event

        return SendJoinResult(
            event,
            self.room_id.domain,
            state=state,
            auth_chain=auth_chain,
            partial_state=False,
            servers_in_room=frozenset(),
        )

    def create_event(self) -> EventBase:
        """
        The fake creation event for this room. Adds itself to the state map and becomes
        the first 'prev_event'
        """
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": "m.room.create",
            "state_key": "",
            "sender": self.creator_id,
            "content": {
                "creator": self.creator_id,
                "m.federate": True,
                "room_version": self.room_version.identifier,
            },
            "auth_events": [],
            "prev_events": [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        event = make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )
        self.map_of_state_events_by_type[EventTypes.Create] = event
        self.auth_events_list.append(event)
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1

        return event

    def creator_member_event(self) -> EventBase:
        """
        The fake join membership event for the creator of this room. Adds itself to the
        membership state map
        """

        auth_events = [e.event_id for e in self.auth_events_list]
        event = self._member_event(
            self.creator_id,
            Membership.JOIN,
            self.creator_id,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        self.map_of_membership_by_mxid[self.creator_id] = event
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return event

    def initial_power_levels_event(self) -> EventBase:
        """
        The fake m.room.power_levels event for this room. Adds itself to the state map
        """
        auth_events = [e.event_id for e in self.auth_events_list]
        # power_levels require the creator member event(or whoever made the event itself) in auth
        auth_events.append(self.map_of_membership_by_mxid[self.creator_id].event_id)
        event = self._power_levels_event(
            self.creator_id,
            content=default_power_level_events(self.creator_id),
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        self.map_of_state_events_by_type[EventTypes.PowerLevels] = event
        self.auth_events_list.append(event)
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return event

    def initial_join_rules_event(self, join_rule: str) -> EventBase:
        auth_events = [e.event_id for e in self.auth_events_list]
        auth_events.append(self.map_of_membership_by_mxid[self.creator_id].event_id)

        event = self._join_rules_event(
            self.creator_id,
            join_rule,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        self.map_of_state_events_by_type[EventTypes.JoinRules] = event
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return event

    def initial_history_visibility_event(self, history_visibility: str) -> EventBase:
        auth_events = [e.event_id for e in self.auth_events_list]
        auth_events.append(self.map_of_membership_by_mxid[self.creator_id].event_id)

        event = self._history_visibility_event(
            self.creator_id,
            history_visibility=history_visibility,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        self.map_of_state_events_by_type[EventTypes.RoomHistoryVisibility] = event
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return event

    def initial_guest_access_event(self, guest_access: str) -> EventBase:
        auth_events = [e.event_id for e in self.auth_events_list]
        auth_events.append(self.map_of_membership_by_mxid[self.creator_id].event_id)

        event = self._guest_access_event(
            self.creator_id,
            guest_access=guest_access,
            auth_events=auth_events,
            prev_events=self.current_prev_events_id_list,
        )
        self.map_of_state_events_by_type[EventTypes.GuestAccess] = event
        self.current_prev_events_id_list = [event.event_id]
        self.depth_counter += 1
        return event

    # Boiler plate event construction is below
    def _member_event(
        self,
        target_user_id: str,
        membership: str,
        sender: str | None = None,
        additional_content: dict | None = None,
        auth_events: list[str] | None = None,
        prev_events: list[str] | None = None,
    ) -> EventBase:
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": EventTypes.Member,
            "sender": sender,
            "state_key": target_user_id,
            "content": {"membership": membership, **(additional_content or {})},
            "auth_events": auth_events or [],
            "prev_events": prev_events or [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )
        return make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )

    def _power_levels_event(
        self,
        sender: str,
        content: dict[str, Any],
        auth_events: list[str] | None = None,
        prev_events: list[str] | None = None,
    ) -> EventBase:
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": EventTypes.PowerLevels,
            "sender": sender,
            "state_key": "",
            "content": content,
            "auth_events": auth_events or [],
            "prev_events": prev_events or [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        return make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )

    def _join_rules_event(
        self,
        sender: str,
        join_rule: str,
        auth_events: list[str] | None = None,
        prev_events: list[str] | None = None,
    ) -> EventBase:
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": EventTypes.JoinRules,
            "sender": sender,
            "state_key": "",
            "content": {
                "join_rule": join_rule,
            },
            "auth_events": auth_events or [],
            "prev_events": prev_events or [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        return make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )

    def _history_visibility_event(
        self,
        sender: str,
        history_visibility: str = "invited",
        auth_events: list[str] | None = None,
        prev_events: list[str] | None = None,
    ) -> EventBase:
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": EventTypes.RoomHistoryVisibility,
            "sender": sender,
            "state_key": "",
            "content": {
                "history_visibility": history_visibility,
            },
            "auth_events": auth_events or [],
            "prev_events": prev_events or [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        return make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )

    def _guest_access_event(
        self,
        sender: str,
        guest_access: str = "can_join",
        auth_events: list[str] | None = None,
        prev_events: list[str] | None = None,
    ) -> EventBase:
        pdu = {
            "room_id": self.room_id.to_string(),
            "depth": self.depth_counter,
            "type": EventTypes.GuestAccess,
            "sender": sender,
            "state_key": "",
            "content": {
                "guest_access": guest_access,
            },
            "auth_events": auth_events or [],
            "prev_events": prev_events or [],
            "origin_server_ts": self.clock.time_msec(),
        }
        add_hashes_and_signatures(
            self.room_version,
            pdu,
            self.server_name_this_room_is_on,
            self.signing_key,
        )

        return make_event_from_dict(
            pdu,
            room_version=self.room_version,
        )


def default_power_level_events(creator_id: str) -> dict[str, Any]:
    power_level_content = {
        "users": {creator_id: 100},
        "users_default": 0,
        "events": {
            EventTypes.Name: 50,
            EventTypes.PowerLevels: 100,
            EventTypes.RoomHistoryVisibility: 100,
            EventTypes.CanonicalAlias: 50,
            EventTypes.RoomAvatar: 50,
            EventTypes.Tombstone: 100,
            EventTypes.ServerACL: 100,
            EventTypes.RoomEncryption: 100,
        },
        "events_default": 0,
        "state_default": 50,
        "ban": 50,
        "kick": 50,
        "redact": 50,
        # For our purposes, the only diff between public and private is that invite is 0 instead of 50
        "invite": 0,
        "historical": 100,
    }
    return power_level_content


def strip_state_event(pdu: dict[str, Any]) -> dict[str, Any]:
    """
    A stripped state event should only have:
      * type
      * state_key
      * sender
      * content
    """
    new_pdu = {}
    for pdu_key in ("type", "state_key", "sender", "content"):
        new_pdu.update({pdu_key: pdu[pdu_key]})
    return new_pdu
