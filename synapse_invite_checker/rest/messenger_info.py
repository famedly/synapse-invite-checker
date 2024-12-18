# Copyright (C) 2020,2024 Famedly
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
from http import HTTPStatus

from synapse.http.servlet import RestServlet
from synapse.http.site import SynapseRequest
from synapse.types import JsonDict

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.rest.base import (
    INFO_API_PREFIX,
    invite_checker_pattern,
)


class MessengerInfoResource(RestServlet):
    def __init__(self, config: InviteCheckerConfig, version: str):
        super().__init__()
        self.config = config
        self.version = version
        self.PATTERNS = invite_checker_pattern("$", INFO_API_PREFIX)

    # @override
    async def on_GET(self, _: SynapseRequest) -> tuple[int, JsonDict]:
        return HTTPStatus.OK, {
            "title": self.config.title,
            "description": self.config.description,
            "contact": self.config.contact,
            "version": self.version,
        }
