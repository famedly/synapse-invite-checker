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
import logging
import re
from dataclasses import dataclass
from http import HTTPStatus
from collections import defaultdict
from typing import Literal, List, Set

from pydantic import BaseModel, ConfigDict, ValidationError
from synapse.api.constants import AccountDataTypes
from synapse.http.server import JsonResource
from synapse.http.servlet import RestServlet, parse_and_validate_json_object_from_request
from synapse.http.site import SynapseRequest
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.types import JsonDict, UserID

logger = logging.getLogger(__name__)

class InviteSettings(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore", allow_inf_nan=False)

    start: int
    end: int | None = None

class Contact(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore", allow_inf_nan=False)

    displayName: str # noqa: N815
    mxid: str
    inviteSettings: InviteSettings # noqa: N815

class Contacts(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore", allow_inf_nan=False)

    contacts : list[Contact]


@dataclass
class InviteCheckerConfig:
    api_prefix: str = "/_synapse/client/com.famedly/tim/v1"
    title: str = "Invite Checker module by Famedly"
    description: str = "Invite Checker module by Famedly"
    contact: str = "info@famedly.com"


class InviteChecker:
    __version__ = "0.0.1"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self._contacts_by_user: dict[UserID, List[Contact]] = defaultdict(lambda: [])
        self.api = api

        self.config = config
        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)

        self.resource = JsonResource(api._hs)

        InfoResource(self).register(self.resource)
        ContactsResource(self).register(self.resource)
        ContactResource(self).register(self.resource)

        self.api.register_web_resource(f"{config.api_prefix}", self.resource)
        logger.info("Module initialized at %s", config.api_prefix)

    @staticmethod
    def parse_config(config):
        logger.error("PARSE CONFIG")
        _config = InviteCheckerConfig()

        _config.api_prefix = config.get(
            "api_prefix", "/_synapse/client/com.famedly/tim/v1"
        )
        _config.title = config.get("title", _config.title)
        _config.description = config.get("description", _config.description)
        _config.contact = config.get("contact", _config.contact)

        return _config

    async def user_may_invite(
        self, inviter: str, invitee: str, room_id: str
    ) -> Literal["NOT_SPAM"] | errors.Codes:
        if self.api.is_mine(inviter):
            direct = await self.api.account_data_manager.get_global(inviter, AccountDataTypes.DIRECT)
            if direct:
                for user, roomids in direct.items():
                    if room_id in roomids and user != invitee:
                        # Can't invite to DM!
                        return errors.Codes.FORBIDDEN

            # local invites are always valid, if they are not to a dm
            if self.api.is_mine(invitee):
                return NOT_SPAM

        # TODO(Nico): implement remaining rules
        return errors.Codes.FORBIDDEN

    def get_contacts(self, user: UserID) -> Contacts:
        if user in self._contacts_by_user:
            return Contacts(contacts=self._contacts_by_user[user])
        return Contacts(contacts=[])

    def del_contact(self, user: UserID, contact: str) -> None:
        self._contacts_by_user[user] = [item for item in  self._contacts_by_user[user] if item.mxid != contact]

    def add_contact(self, user: UserID, contact: Contact) -> None:
        self.del_contact(user, contact.mxid)
        self._contacts_by_user[user].append(contact)

    def get_contact(self, user: UserID, mxid: str) -> Contact | None:
        for contact in self._contacts_by_user[user]:
            if contact.mxid == mxid:
                return contact
        return None


def invite_checker_pattern(path_regex: str, config: InviteCheckerConfig):
    path = path_regex.removeprefix("/")
    root = config.api_prefix.removesuffix("/")
    raw_regex = f"^{root}/{path}"

    # we need to strip the /$, otherwise we can't register for the root of the prefix in a handler...
    if raw_regex.endswith("/$"):
        raw_regex = raw_regex.replace("/$", "$")

    return [re.compile(raw_regex)]


class InfoResource(RestServlet):
    def __init__(self, checker: InviteChecker):
        super().__init__()
        self.checker = checker
        self.PATTERNS = invite_checker_pattern("$", self.checker.config)

    # @override
    async def on_GET(self, _: SynapseRequest) -> tuple[int, JsonDict]:
        return HTTPStatus.OK, {
            "title": self.checker.config.title,
            "description": self.checker.config.description,
            "contact": self.checker.config.contact,
            "version": self.checker.__version__,
        }

class ContactsResource(RestServlet):
    def __init__(self, checker: InviteChecker):
        super().__init__()
        self.checker = checker
        self.PATTERNS = invite_checker_pattern("/contacts$", self.checker.config)

    # @override
    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        requester = await self.checker.api.get_user_by_req(request)
        return HTTPStatus.OK, self.checker.get_contacts(requester.user).model_dump()

    async def on_POST(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        return await self.on_PUT(request)

    async def on_PUT(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        requester = await self.checker.api.get_user_by_req(request)

        try:
            contact = parse_and_validate_json_object_from_request(request, Contact)
            self.checker.add_contact(requester.user, contact)
        except (errors.SynapseError, ValidationError) as e:
            raise errors.SynapseError(
                    HTTPStatus.BAD_REQUEST,
                    "Missing required field",
                    errors.Codes.BAD_JSON,
                    ) from e

        return HTTPStatus.OK, contact.model_dump()

class ContactResource(RestServlet):
    def __init__(self, checker: InviteChecker):
        super().__init__()
        self.checker = checker
        self.PATTERNS = invite_checker_pattern("/contacts/(?P<mxid>[^/]*)$", self.checker.config)

    # @override
    async def on_GET(self, request: SynapseRequest, mxid: str) -> tuple[int, JsonDict]:
        requester = await self.checker.api.get_user_by_req(request)

        contact = self.checker.get_contact(requester.user, mxid)
        if contact:
            return HTTPStatus.OK, contact.model_dump()
        else:
            return HTTPStatus.NOT_FOUND, {}


    async def on_DELETE(self, request: SynapseRequest, mxid: str) -> tuple[int, JsonDict]:
        requester = await self.checker.api.get_user_by_req(request)

        contact = self.checker.get_contact(requester.user, mxid)
        if contact:
            self.checker.del_contact(requester.user, mxid)
            return HTTPStatus.NO_CONTENT, {}
        else:
            return HTTPStatus.NOT_FOUND, {}

