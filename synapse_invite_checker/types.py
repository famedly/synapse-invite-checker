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


from pydantic import BaseModel, ConfigDict


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
