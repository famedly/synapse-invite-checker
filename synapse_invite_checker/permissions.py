# SPDX-FileCopyrightText: 2026 Famedly GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only
import logging
from collections.abc import Awaitable, Callable

from pydantic import ValidationError
from synapse.module_api import ModuleApi
from synapse.types import UserID

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.types import PermissionConfig, PermissionConfigType, TimType

logger = logging.getLogger(__name__)


class InviteCheckerPermissionsHandler:
    """
    Used to retrieve and store permissions for users while taking into account the event type
    of configuration as required by gematik spec.

    A great deal of this can be removed after the Contacts REST Api has been removed
    """

    def __init__(
        self,
        api: ModuleApi,
        config: InviteCheckerConfig,
        is_domain_insurance_cb: Callable[[str], Awaitable[bool]],
        default_perms_from_config: PermissionConfig,
    ) -> None:
        self.api = api
        self.config = config
        self.account_data_manager = self.api.account_data_manager
        self.is_domain_insurance = is_domain_insurance_cb
        self.default_perms = default_perms_from_config

    async def get_permissions(self, user_id: str) -> PermissionConfig:
        config_type = self.permission_event_type()
        account_data = await self.account_data_manager.get_global(
            user_id, config_type.value
        )
        if not account_data or not account_data.get("defaultSetting"):
            # Overwrite or set the permissions in three cases(two here, third below):
            # 1. No existing permissions or if they are misconfigured as {}
            # 2. The defaultSetting key is missing, indicating a broken permission structure
            permissions = self.default_perms
            logger.debug("Setting default/initial permissions for user '%s'", user_id)
            await self.update_permissions(user_id, permissions)
        else:
            try:
                permissions = PermissionConfig.model_validate(account_data)
            except ValidationError as e:
                # 3. Somehow the json was incomplete or got mangled, set the default as a
                # 'reset action'
                logger.warning(
                    "Permissions for %s found to be broken, resetting as default: %r",
                    user_id,
                    e,
                )
                permissions = self.default_perms
                await self.update_permissions(user_id, permissions)

        return permissions

    async def update_permissions(
        self,
        user_id: str,
        permissions: PermissionConfig,
    ) -> None:
        config_type = self.permission_event_type()
        await self.account_data_manager.put_global(
            user_id,
            config_type.value,
            permissions.dump(),
        )

    def permission_event_type(self) -> PermissionConfigType:
        """
        Convert the TIM server type into the appropriate user permission event type
        """
        if self.config.tim_type == TimType.EPA:
            config_type = PermissionConfigType.EPA_ACCOUNT_DATA_TYPE
        else:
            # Since we default to PRO, this seems prudent unless a better option
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
