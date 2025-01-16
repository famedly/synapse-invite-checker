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
from enum import Enum, auto
from functools import cached_property
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, computed_field
from synapse.types import UserID


class InviteSettings(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    start: int
    end: int | None = None


class Contact(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    displayName: str  # noqa: N815
    mxid: str
    inviteSettings: InviteSettings  # noqa: N815


class Contacts(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    contacts: list[Contact]


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

    # I believe that it should be correct to set the default value here, but the method
    # used to extract the data later(see dump() below, specifically 'exclude_defaults=True')
    # will then not include it. Imported data does not have this issue. See
    # InviteCheckerPermissionsHandler.get_permissions() for where it is set now.
    # TLDR: this will not be an important detail after migrations have run as it will
    # always be set during class instantiation
    defaultSetting: PermissionDefaultSetting = None
    # If any of these three exists, they should contain a dict with the key as the
    # exception and then an empty dict inside "for future expansion"
    serverExceptions: Annotated[dict[str, dict], Field(default_factory=dict)] = None
    # If there is a key inside userExceptions, it needs to be sure to start with a '@'.
    # Should we validate this or trust the client app does the right thing?
    userExceptions: Annotated[dict[str, dict], Field(default_factory=dict)] = None
    groupExceptions: Annotated[list[dict[str, str]], Field(default_factory=list)] = None

    def maybe_get_contact(self, mxid: str) -> Contact | None:
        """
        Used by the Contact REST Api to look like a Contact.
        """
        # Will be removed after Contacts API has been deprecated
        if mxid in self.userExceptions:
            return Contact(
                displayName="",
                mxid=mxid,
                inviteSettings=InviteSettings(start=0, end=None),
            )
        return None

    def get_contacts(self) -> Contacts:
        """
        Used by the Contacts REST Api to look like a Contacts
        """
        return Contacts(
            contacts=[
                Contact(
                    # Not certain what to use for displayName, that data isn't
                    # available anymore. I think the client has to sort it out
                    displayName="",
                    mxid=mxid,
                    inviteSettings=InviteSettings(start=0, end=None),
                )
                for mxid in self.userExceptions
            ]
        )

    def dump(self) -> dict[str, Any]:
        # exclude_none=True strips out the attributes that are None so they do translate
        # to JSON as 'null'. exclude_defaults=True strips out attributes in the same
        # way. It does not touch empty dict sub-attributes only top level!!
        # mode="json" turns the classes into their string names.
        return self.model_dump(mode="json", exclude_none=True, exclude_defaults=True)

    def is_allow_all(self):
        return self.defaultSetting == PermissionDefaultSetting.ALLOW_ALL.value

    def is_mxid_allowed_to_contact(self, mxid: str, is_mxid_epa: bool) -> bool:
        """
        The main test for allowing or blocking an invitation.
        """
        mxid_domain = UserID.from_string(mxid).domain
        allowed = self.is_allow_all()

        if is_mxid_epa and self.is_group_excepted(GroupName.isInsuredPerson):
            allowed = not allowed

        elif mxid_domain in self.serverExceptions:
            allowed = not allowed
        elif mxid in self.userExceptions:
            allowed = not allowed

        return allowed

    def is_group_excepted(self, group_name: GroupName) -> bool:
        return any(
            True
            for groupException in self.groupExceptions
            if groupException.get("groupName") == group_name.value
        )


class FederationDomain(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    domain: str
    telematikID: str  # noqa: N815
    timAnbieter: str | None  # noqa: N815
    isInsurance: bool  # noqa: N815


class FederationList(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="ignore", allow_inf_nan=False
    )

    domainList: list[FederationDomain]  # noqa: N815

    @computed_field
    @cached_property
    def _domains_on_list(self) -> set[str]:
        """
        The deduplicated domains found on the Federation List
        """
        return {domain_data.domain for domain_data in self.domainList}

    @computed_field
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


class TimType(Enum):
    PRO = auto()
    EPA = auto()


class PermissionConfigType(Enum):
    EPA_ACCOUNT_DATA_TYPE = "de.gematik.tim.account.permissionconfig.epa.v1"
    PRO_ACCOUNT_DATA_TYPE = "de.gematik.tim.account.permissionconfig.pro.v1"
