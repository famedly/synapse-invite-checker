# Copyright (C) 2025 Famedly
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
from collections.abc import Awaitable, Callable

from synapse.module_api import ModuleApi
from synapse.types import UserID

from synapse_invite_checker.types import (
    DefaultPermissionConfig,
    PermissionConfig,
    PermissionConfigType,
)


class InviteCheckerPermissionsHandler:
    """
    Used to retrieve and store permissions for users while taking into account the event type
    of configuration as required by gematik spec.

    A great deal of this can be removed after the Contacts REST Api has been removed
    """

    def __init__(
        self,
        api: ModuleApi,
        is_domain_insurance_cb: Callable[[str], Awaitable[bool]],
        default_perms_from_config: DefaultPermissionConfig,
    ) -> None:
        self.api = api
        self.account_data_manager = self.api.account_data_manager
        self.is_domain_insurance = is_domain_insurance_cb
        self.default_perms = default_perms_from_config

    async def get_permissions(self, user_id: str) -> PermissionConfig:
        config_type = await self.get_config_type_from_mxid(user_id)
        account_data = await self.account_data_manager.get_global(
            user_id, config_type.value
        )

        # Overwrite or set the permissions in two cases:
        # 1. No existing permissions or if they are somehow mis-set as {}
        # 2. The defaultSetting key is missing, indicating a broken permission structure
        if not account_data or not account_data.get("defaultSetting"):
            permissions = self.default_perms
            await self.update_permissions(user_id, permissions)
        else:
            permissions = PermissionConfig.model_validate(account_data)
        return permissions

    async def update_permissions(
        self,
        user_id: str,
        permissions: PermissionConfig,
    ) -> None:
        # Will be removed after Contacts API has been deprecated
        config_type = await self.get_config_type_from_mxid(user_id)
        await self.account_data_manager.put_global(
            user_id,
            config_type.value,
            permissions.dump(),
        )

    async def get_config_type_from_mxid(
        self, local_user_id: str
    ) -> PermissionConfigType:
        """
        Identify(as best can be done) what type of local User it is
        """
        local_mxid_domain = UserID.from_string(local_user_id).domain
        # Recall that the request used here is cached from the federation list
        if await self.is_domain_insurance(local_mxid_domain):
            config_type = PermissionConfigType.EPA_ACCOUNT_DATA_TYPE
        else:
            config_type = PermissionConfigType.PRO_ACCOUNT_DATA_TYPE
        return config_type

    async def is_user_allowed(self, local_user_id: str, remote_mxid: str) -> bool:
        """
        The primary check used by InviteChecker's user_may_invite()
        """
        permissions = await self.get_permissions(local_user_id)
        is_remote_mxid_insurance = await self.is_domain_insurance(
            UserID.from_string(remote_mxid).domain
        )
        return permissions.is_mxid_allowed_to_contact(
            remote_mxid, is_mxid_epa=is_remote_mxid_insurance
        )
