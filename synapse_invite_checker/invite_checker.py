# -*- coding: utf-8 -*-
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
from typing import Union, Literal
import logging
from dataclasses import dataclass

from synapse.module_api import ModuleApi, NOT_SPAM, errors

from twisted.web.resource import Resource
from twisted.web.server import Request
import json

logger = logging.getLogger(__name__)


@dataclass
class InviteCheckerConfig:
    api_prefix: str = '/_synapse/client/com.famedly/tim/v1'
    title: str = 'Invite Checker module by Famedly'
    description: str = 'Invite Checker module by Famedly'
    contact: str = 'info@famedly.com'


class InviteChecker:
    __version__ = "0.0.1"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self.api = api

        self.config = config
        self.api.register_spam_checker_callbacks(
                user_may_invite=self.user_may_invite
                )
        self.api.register_web_resource(f'{config.api_prefix}', InfoResource(self))
        logger.info(f"Module initialized at {config.api_prefix}")

    # pylint: disable=unused-argument
    async def user_may_invite(
            self, inviter: str, invitee: str, room_id: str
            ) -> Union[Literal["NOT_SPAM"], errors.Codes]:
        #if self.config.block_all_outgoing_invites and self.api.is_mine(inviter):
        #    print(f"is mine {inviter}")
        #    return errors.Codes.FORBIDDEN
        return NOT_SPAM

    @staticmethod
    def parse_config(config):
        logger.error("PARSE CONFIG")
        _config = InviteCheckerConfig()

        _config.api_prefix = config.get(
                "api_prefix", '/_synapse/client/com.famedly/tim/v1'
                )
        _config.title = config.get("title", _config.title)
        _config.description = config.get("description", _config.description)
        _config.contact = config.get("contact", _config.contact)

        return _config

class InfoResource(Resource):
    def __init__(self, checker: InviteChecker):
        super(InfoResource, self).__init__()
        self.checker = checker

    #@override
    def render_GET(self, _: Request):
        return json.dumps({
            "title": self.checker.config.title,
            "description": self.checker.config.description,
            "contact": self.checker.config.contact,
            "version": self.checker.__version__,
            }).encode()

