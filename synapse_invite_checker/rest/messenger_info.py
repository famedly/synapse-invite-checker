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
import re
from http import HTTPStatus
from typing import Awaitable, Callable, List

from synapse.http.servlet import RestServlet, parse_string
from synapse.http.site import SynapseRequest
from synapse.module_api import errors
from synapse.types import JsonDict

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.rest.base import invite_checker_pattern
from synapse_invite_checker.types import TimType

# Version of TiMessengerInformation interface. See:
# https://github.com/gematik/api-ti-messenger/blob/main/src/openapi/TiMessengerInformation.yaml
_TMI_schema_version = "1.0.0"

INFO_API_PREFIX = "/tim-information"


def tim_info_patterns(path_regex: str) -> List[re.Pattern]:
    return invite_checker_pattern(INFO_API_PREFIX, path_regex)


class MessengerInfoResource(RestServlet):
    def __init__(self, config: InviteCheckerConfig):
        super().__init__()
        self.config = config
        self.version = _TMI_schema_version

        self.PATTERNS = tim_info_patterns("/$")

    async def on_GET(self, _: SynapseRequest) -> tuple[int, JsonDict]:
        return HTTPStatus.OK, {
            "title": self.config.title,
            "description": self.config.description,
            "contact": self.config.contact,
            "version": self.version,
        }


class MessengerIsInsuranceResource(RestServlet):
    def __init__(
        self,
        config: InviteCheckerConfig,
        is_insurance_cb: Callable[[str], Awaitable[bool]],
    ):
        super().__init__()
        self.config = config
        self.is_insurance_cb = is_insurance_cb

        self.PATTERNS = tim_info_patterns("/v1/server/isInsurance$")

    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        if self.config.tim_type == TimType.EPA:
            return 401, {
                "errorCode": errors.Codes.UNAUTHORIZED,
                "errorMessage": "Unauthorized to access for ePA backend",
            }

        server_name = parse_string(request, "serverName", required=True)
        isInsurance = await self.is_insurance_cb(server_name)
        return HTTPStatus.OK, {
            "isInsurance": isInsurance,
        }
