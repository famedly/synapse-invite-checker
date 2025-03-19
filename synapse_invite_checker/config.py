# Copyright (C) 2020,2023 Famedly
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
from dataclasses import dataclass, field


from synapse_invite_checker.types import DefaultPermissionConfig, TimType


@dataclass
class InsuredOnlyRoomScanConfig:
    grace_period_ms: int = 0
    enabled: bool = False


@dataclass
class InactiveRoomScanConfig:
    grace_period_ms: int = 0
    enabled: bool = False


@dataclass
class InviteCheckerConfig:
    title: str = "Invite Checker module by Famedly"
    description: str = "Invite Checker module by Famedly"
    contact: str = "info@famedly.com"
    federation_list_url: str = ""
    federation_list_client_cert: str = ""
    gematik_ca_baseurl: str = ""
    tim_type: TimType = TimType.PRO
    allowed_room_versions: list[str] = field(default_factory=list)
    room_scan_run_interval_ms: int = 0
    insured_room_scan_options: InsuredOnlyRoomScanConfig = field(
        default_factory=InsuredOnlyRoomScanConfig
    )
    inactive_room_scan_options: InactiveRoomScanConfig = field(
        default_factory=InactiveRoomScanConfig
    )
    override_public_room_federation: bool = True
    prohibit_world_readable_rooms: bool = True
    block_invites_into_dms: bool = True
    default_permissions: DefaultPermissionConfig = None
