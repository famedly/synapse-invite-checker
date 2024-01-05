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
from typing import Literal

from synapse.http.server import JsonResource
from synapse.http.servlet import RestServlet
from synapse.http.site import SynapseRequest
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.types import JsonDict

logger = logging.getLogger(__name__)


@dataclass
class InviteCheckerConfig:
    api_prefix: str = "/_synapse/client/com.famedly/tim/v1"
    title: str = "Invite Checker module by Famedly"
    description: str = "Invite Checker module by Famedly"
    contact: str = "info@famedly.com"


class InviteChecker:
    __version__ = "0.0.1"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self.api = api

        self.config = config
        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)
        # self.api.register_web_resource(f'{config.api_prefix}', InfoResource(self))
        self.resource = JsonResource(api._hs)
        InfoResource(self).register(self.resource)
        self.api.register_web_resource(f"{config.api_prefix}", self.resource)
        logger.info("Module initialized at %s", config.api_prefix)

    # pylint: disable=unused-argument
    async def user_may_invite(
        self, inviter: str, invitee: str, room_id: str
    ) -> Literal["NOT_SPAM"] | errors.Codes:
        # if self.config.block_all_outgoing_invites and self.api.is_mine(inviter):
        #    print(f"is mine {inviter}")
        #    return errors.Codes.FORBIDDEN
        return NOT_SPAM

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
    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        return HTTPStatus.OK, {
            "title": self.checker.config.title,
            "description": self.checker.config.description,
            "contact": self.checker.config.contact,
            "version": self.checker.__version__,
        }
