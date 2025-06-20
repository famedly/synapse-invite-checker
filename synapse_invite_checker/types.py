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
from dataclasses import dataclass
from enum import Enum, auto
from functools import cached_property
from typing import Any, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)
from synapse.types import UserID


class PermissionDefaultSetting(Enum):
    ALLOW_ALL = "allow all"
    BLOCK_ALL = "block all"


class GroupName(Enum):
    isInsuredPerson = "isInsuredPerson"


class PermissionConfig(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        allow_inf_nan=False,
        use_enum_values=True,
    )

    # This is where we will set the default permission setting now. This only is used
    # when the template is not produced in the configuration, per README.md
    defaultSetting: PermissionDefaultSetting = PermissionDefaultSetting.ALLOW_ALL
    # If either of these two exist, they should contain a dict with the key as the
    # exception and then an empty dict inside "for future expansion"
    serverExceptions: dict[str, dict] = Field(default_factory=dict)
    # If there is a key inside userExceptions, it needs to be sure to start with a '@'.
    # Should we validate this or trust the client app does the right thing?
    userExceptions: dict[str, dict] = Field(default_factory=dict)
    # This is slightly different to the two just above, as it uses a list to contain the
    # dict. At time of writing there is exactly one option, and it is part of the
    # GroupName enum class just above
    groupExceptions: list[dict[str, str]] = Field(default_factory=list)

    def dump(self) -> dict[str, Any]:
        # exclude_unset=True strips out the attributes that were never set, and thus
        # will not appear in the JSON. It does not touch empty dict sub-attributes only
        # top level!!
        # mode="json" which effectively keeps the camel casing for us(as that is a
        # gematik requirement) and makes sure the keys remain as strings.
        return self.model_dump(mode="json", exclude_unset=True)

    def is_allow_all(self):
        return self.defaultSetting != PermissionDefaultSetting.BLOCK_ALL.value

    def is_mxid_allowed_to_contact(self, mxid: str, is_mxid_epa: bool) -> bool:
        """
        The main test for allowing or blocking an invitation.
        """
        mxid_domain = UserID.from_string(mxid).domain
        allowed = self.is_allow_all()

        if (
            is_mxid_epa
            and self.is_group_excepted(GroupName.isInsuredPerson)
            or mxid_domain in self.serverExceptions
            or mxid in self.userExceptions
        ):
            allowed = not allowed

        return allowed

    def is_group_excepted(self, group_name: GroupName) -> bool:
        return any(
            True
            for groupException in self.groupExceptions
            if groupException.get("groupName") == group_name.value
        )


LOCAL_SERVER_TEMPLATE: Final[str] = "@LOCAL_SERVER@"


class DefaultPermissionConfig(PermissionConfig):
    """
    Extend PermissionConfig to include a few additional necessities. Use a
    @field_validator() call to set the objects required per gematik spec on the sub-keys
    of serverExceptions and userExceptions. This way can avoid having to hard-wire a '
    {}' into the generated configuration for the module
    """

    @field_validator("serverExceptions", "userExceptions", mode="before")
    @staticmethod
    def transform_field(keys: dict) -> dict:
        """
        This will run on model_validate(and it's variants) to transform the fields to
        include the required empty object as the value per gematik spec.
        """
        # Use this to transform the fields in PermissionConfig from(for example):
        # {"serverExceptions": {"server_name.com": None}}
        # to
        # {"serverExceptions": {"server_name.com": {}}}
        for key, value in dict(keys).items():
            if value is None:
                keys[key] = {}
        return keys

    def maybe_update_server_exceptions(self, local_server_name: str) -> None:
        """
        Swap out the template variable assigned by LOCAL_SERVER_TEMPLATE(above) to
        register the *actual* local server name
        Args:
            local_server_name: the local server name

        Returns: None
        """
        if LOCAL_SERVER_TEMPLATE in self.serverExceptions:
            self.serverExceptions.setdefault(
                local_server_name, self.serverExceptions.get(LOCAL_SERVER_TEMPLATE, {})
            )
            del self.serverExceptions[LOCAL_SERVER_TEMPLATE]


class FederationDomain(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    domain: str
    telematikID: str
    timAnbieter: str | None
    isInsurance: bool
    # ik gets marked as 'strict=False' as not all domains will have that data
    ik: list[str] = Field(default_factory=list, strict=False)


class FederationList(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    domainList: list[FederationDomain]

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def _domains_on_list(self) -> set[str]:
        """
        The deduplicated domains found on the Federation List
        """
        return {domain_data.domain for domain_data in self.domainList}

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def _insurance_domains_on_list(self) -> set[str]:
        """
        Only the domains that are also type 'isInsurance'
        """
        return {
            domain_data.domain
            for domain_data in self.domainList
            if domain_data.isInsurance
        }

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def _ik_to_domain(self) -> dict[str, str]:
        """
        A reverse lookup mapping for ik->serverName
        """
        ik_mapping = {}
        for domain in self.domainList:
            if domain.isInsurance:
                # I believe that this creates an empty dict if the data isn't present
                ik_mapping.update({ik: domain.domain for ik in domain.ik})
        return ik_mapping

    def allowed(self, domain: str) -> bool:
        """
        Compare against the domains from the Federation List to determine if they are allowed
        """
        return domain in self._domains_on_list

    def is_insurance(self, domain: str) -> bool:
        """
        Is this domain specifically designated as 'isInsurance'
        """
        return domain in self._insurance_domains_on_list

    def get_domain_from_ik(self, ik: str) -> str | None:
        return self._ik_to_domain.get(ik)


class TimType(Enum):
    PRO = auto()
    EPA = auto()


class PermissionConfigType(Enum):
    EPA_ACCOUNT_DATA_TYPE = "de.gematik.tim.account.permissionconfig.epa.v1"
    PRO_ACCOUNT_DATA_TYPE = "de.gematik.tim.account.permissionconfig.pro.v1"


@dataclass(slots=True)
class EpaRoomTimestampResults:
    """
    Collection of timestamps used to decide if a room should have members removed.
    Used for EPA server rooms. Recall that invite/leave timestamps are *only* seeded
    from pro users membership events

    Attributes:
        last_invite_in_room: The timestamp for the newest 'invite' membership in the
            room. Only used if there was no detected 'leave' event.
        last_leave_in_room: The timestamp of the newest 'leave' membership in the room.
            The preferred timestamp to acquire.
        room_creation_ts: If nothing else, use the room creation as a sentinel. The slim
            possibility exists that no 'leave' event exists and any 'invite' may have
            failed. This is allowed to give a user time to try again before they do not
            have access to this room removed.
    """

    last_invite_in_room: int | None = None
    last_leave_in_room: int | None = None
    room_creation_ts: int | None = None
