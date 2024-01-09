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
from typing import Literal

from synapse.api.constants import AccountDataTypes
from synapse.http.server import JsonResource
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.storage.database import make_conn

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.handlers import ContactResource, ContactsResource, InfoResource
from synapse_invite_checker.store import InviteCheckerStore

logger = logging.getLogger(__name__)

# ruff: noqa: SLF001


class InviteChecker:
    __version__ = "0.0.1"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self.api = api

        self.config = config
        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)

        self.resource = JsonResource(api._hs)

        dbconfig = None
        for dbconf in api._store.config.database.databases:
            if dbconf.name == "master":
                dbconfig = dbconf

        if not dbconfig:
            msg = "missing database config"
            raise Exception(msg)

        with make_conn(dbconfig, api._store.database_engine, "invite_checker_startup") as db_conn:
            self.store = InviteCheckerStore(api._store.db_pool, db_conn, api._hs)

        InfoResource(self.config, self.__version__).register(self.resource)
        ContactsResource(self.api, self.store, self.config).register(self.resource)
        ContactResource(self.api, self.store, self.config).register(self.resource)

        self.api.register_web_resource(f"{config.api_prefix}", self.resource)
        logger.info("Module initialized at %s", config.api_prefix)

    @staticmethod
    def parse_config(config):
        logger.error("PARSE CONFIG")
        _config = InviteCheckerConfig()

        _config.api_prefix = config.get("api_prefix", "/_synapse/client/com.famedly/tim/v1")
        _config.title = config.get("title", _config.title)
        _config.description = config.get("description", _config.description)
        _config.contact = config.get("contact", _config.contact)

        return _config

    async def user_may_invite(self, inviter: str, invitee: str, room_id: str) -> Literal["NOT_SPAM"] | errors.Codes:
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
