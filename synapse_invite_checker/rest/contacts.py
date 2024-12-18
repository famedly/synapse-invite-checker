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
from typing import List

from pydantic import ValidationError
from synapse.http.servlet import (
    RestServlet,
    parse_and_validate_json_object_from_request,
)
from synapse.http.site import SynapseRequest
from synapse.module_api import ModuleApi, errors
from synapse.types import JsonDict

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.rest.base import invite_checker_pattern
from synapse_invite_checker.store import InviteCheckerStore
from synapse_invite_checker.types import Contact

# Version of the TiMessengerContactManagement interface. See:
# https://github.com/gematik/api-ti-messenger/blob/main/src/openapi/TiMessengerContactManagement.yaml
_TMCM_schema_version = "1.0.2"

# This API prefix will probably be deprecated in the future
CONTACT_MANAGEMENT_API_PREFIX = "/_synapse/client/com.famedly/tim/v1"


def contact_mgmt_patterns(pattern: str) -> List[re.Pattern]:
    return invite_checker_pattern(CONTACT_MANAGEMENT_API_PREFIX, pattern)


class ContactManagementInfoResource(RestServlet):
    def __init__(self, config: InviteCheckerConfig):
        super().__init__()
        self.config = config
        self.version = _TMCM_schema_version
        self.PATTERNS = contact_mgmt_patterns("/$")

    # @override
    async def on_GET(self, _: SynapseRequest) -> tuple[int, JsonDict]:
        return HTTPStatus.OK, {
            "title": self.config.title,
            "description": self.config.description,
            "contact": self.config.contact,
            "version": self.version,
        }


class ContactsResource(RestServlet):
    def __init__(self, api: ModuleApi, store: InviteCheckerStore):
        super().__init__()
        self.store = store
        self.api = api
        self.PATTERNS = contact_mgmt_patterns("/contacts$")

    # @override
    async def on_GET(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        requester = await self.api.get_user_by_req(request)
        return (
            HTTPStatus.OK,
            (await self.store.get_contacts(requester.user)).model_dump(),
        )

    async def on_POST(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        return await self.on_PUT(request)

    async def on_PUT(self, request: SynapseRequest) -> tuple[int, JsonDict]:
        requester = await self.api.get_user_by_req(request)

        try:
            contact = parse_and_validate_json_object_from_request(request, Contact)
            await self.store.add_contact(requester.user, contact)
        except (errors.SynapseError, ValidationError) as e:
            raise errors.SynapseError(
                HTTPStatus.BAD_REQUEST,
                "Missing required field",
                errors.Codes.BAD_JSON,
            ) from e

        return HTTPStatus.OK, contact.model_dump()


class ContactResource(RestServlet):
    def __init__(self, api: ModuleApi, store: InviteCheckerStore):
        super().__init__()
        self.store = store
        self.api = api
        self.PATTERNS = contact_mgmt_patterns("/contacts/(?P<mxid>[^/]*)$")

    # @override
    async def on_GET(self, request: SynapseRequest, mxid: str) -> tuple[int, JsonDict]:
        requester = await self.api.get_user_by_req(request)

        contact = await self.store.get_contact(requester.user, mxid)
        if contact:
            return HTTPStatus.OK, contact.model_dump()

        return HTTPStatus.NOT_FOUND, {}

    async def on_DELETE(
        self, request: SynapseRequest, mxid: str
    ) -> tuple[int, JsonDict]:
        requester = await self.api.get_user_by_req(request)

        contact = await self.store.get_contact(requester.user, mxid)
        if contact:
            await self.store.del_contact(requester.user, mxid)
            return HTTPStatus.NO_CONTENT, {}

        return HTTPStatus.NOT_FOUND, {}
