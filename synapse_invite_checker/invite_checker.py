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
from collections import defaultdict
from typing import Literal

from synapse.api.constants import AccountDataTypes
from synapse.http.server import JsonResource
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.types import UserID

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.types import Contact, Contacts

logger = logging.getLogger(__name__)

class InviteChecker:
    __version__ = "0.0.1"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self._contacts_by_user: dict[UserID, list[Contact]] = defaultdict(list)
        self.api = api

        self.config = config
        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)

        self.resource = JsonResource(api._hs)

        from synapse_invite_checker.handlers import ContactsResource, register_handlers
        register_handlers(self, self.resource)
        ContactsResource(self).register(self.resource)

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

