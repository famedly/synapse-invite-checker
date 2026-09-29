# SPDX-FileCopyrightText: 2026 Famedly GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only
import re
from collections.abc import Awaitable, Callable
from http import HTTPStatus

from synapse.http.servlet import RestServlet, parse_string
from synapse.http.site import SynapseRequest
from synapse.module_api import ModuleApi, errors
from synapse.types import JsonDict

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.rest.base import invite_checker_pattern
from synapse_invite_checker.types import FederationList

# Version of TiMessengerInformation interface. See:
# https://github.com/gematik/api-ti-messenger/blob/main/src/openapi/TiMessengerInformation.yaml
_TMI_schema_version = "1.0.0"

INFO_API_PREFIX = "/tim-information"


def tim_info_patterns(path_regex: str) -> list[re.Pattern]:
    return invite_checker_pattern(INFO_API_PREFIX, path_regex)


class MessengerInfoResource(RestServlet):
    def __init__(self, api: ModuleApi, config: InviteCheckerConfig):
        super().__init__()
        self.api = api
        self.config = config
        self.version = _TMI_schema_version

        self.PATTERNS = tim_info_patterns("/$")

    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        # This is just to verify the requester is actually authorized
        await self.api.get_user_by_req(request)
        return HTTPStatus.OK, {
            "title": self.config.title,
            "description": self.config.description,
            "contact": self.config.contact,
            "version": self.version,
        }


class MessengerIsInsuranceResource(RestServlet):
    def __init__(
        self,
        api: ModuleApi,
        config: InviteCheckerConfig,
        is_insurance_cb: Callable[[str], Awaitable[bool]],
    ):
        super().__init__()
        self.api = api
        self.config = config
        self.is_insurance_cb = is_insurance_cb

        self.PATTERNS = tim_info_patterns("/v1/server/isInsurance$")

    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        await self.api.get_user_by_req(request)
        server_name = parse_string(request, "serverName", required=True)
        is_insurance = await self.is_insurance_cb(server_name)
        return HTTPStatus.OK, {
            "isInsurance": is_insurance,
        }


class MessengerFindByIkResource(RestServlet):
    def __init__(
        self,
        api: ModuleApi,
        config: InviteCheckerConfig,
        fed_list_cb: Callable[..., Awaitable[FederationList]],
    ):
        super().__init__()
        self.api = api
        self.config = config
        self.fed_list_cb = fed_list_cb

        self.PATTERNS = tim_info_patterns("/v1/server/findByIk$")

    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        await self.api.get_user_by_req(request)

        ik_num = parse_string(request, "ikNumber", required=True)
        fed_list = await self.fed_list_cb()
        server_name = fed_list.get_domain_from_ik(ik_num)
        if server_name is None:
            return HTTPStatus.NOT_FOUND, {
                "errcode": errors.Codes.NOT_FOUND,
                "error": "ikNumber was not found",
            }
        return HTTPStatus.OK, {
            "serverName": server_name,
        }
