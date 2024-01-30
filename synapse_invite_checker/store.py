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

from synapse.server import HomeServer
from synapse.storage._base import SQLBaseStore
from synapse.storage.database import (
    DatabasePool,
    LoggingDatabaseConnection,
    LoggingTransaction,
)
from synapse.types import UserID

from synapse_invite_checker.types import Contact, Contacts, InviteSettings

logger = logging.getLogger(__name__)


class InviteCheckerStore(SQLBaseStore):
    def __init__(
        self,
        database: DatabasePool,
        db_conn: LoggingDatabaseConnection,
        hs: HomeServer,
    ):
        super().__init__(database, db_conn, hs)

        self.db_checked = False

    async def ensure_table_exists(self):
        if not self.db_checked:

            def ensure_table_exists_txn(txn: LoggingTransaction) -> bool:
                # We need to quote at least the user column on postgres
                sql = """
                    CREATE TABLE IF NOT EXISTS famedly_invite_checker (
                        "user" TEXT NOT NULL,
                        "contact_display_name" TEXT NOT NULL,
                        "contact_mxid" TEXT NOT NULL,
                        "contact_invite_settings_start" BIGINT NOT NULL,
                        "contact_invite_settings_end" BIGINT
                    );
                    """
                txn.execute(sql)
                txn.execute(
                    """
                            CREATE INDEX IF NOT EXISTS famedly_invite_checker_user
                            ON famedly_invite_checker("user");
                            """
                )
                txn.execute(
                    """
                            CREATE UNIQUE INDEX IF NOT EXISTS famedly_invite_checker_user_mxid
                            ON famedly_invite_checker("user", "contact_mxid");
                            """
                )
                return True

            await self.db_pool.runInteraction(
                "ensure_invite_checker_table_exists", ensure_table_exists_txn
            )

            self.db_checked = True

    async def get_contacts(self, user: UserID) -> Contacts:
        await self.ensure_table_exists()
        contacts = await self.db_pool.simple_select_list(
            "famedly_invite_checker",
            keyvalues={"user": user.to_string()},
            retcols=(
                "contact_display_name",
                "contact_mxid",
                "contact_invite_settings_start",
                "contact_invite_settings_end",
            ),
            desc="famedly_invite_checker_get_contacts",
        )
        return Contacts(
            contacts=[
                Contact(
                    displayName=name,
                    mxid=mxid,
                    inviteSettings=InviteSettings(start=start, end=end),
                )
                for (name, mxid, start, end) in contacts
            ]
        )

    async def del_contact(self, user: UserID, contact: str) -> None:
        await self.ensure_table_exists()
        await self.db_pool.simple_delete(
            "famedly_invite_checker",
            {"user": user.to_string(), "contact_mxid": contact},
            desc="famedly_invite_checker_del_contact",
        )

    async def add_contact(self, user: UserID, contact: Contact) -> None:
        await self.ensure_table_exists()
        await self.db_pool.simple_upsert(
            "famedly_invite_checker",
            keyvalues={"user": user.to_string(), "contact_mxid": contact.mxid},
            values={
                "user": user.to_string(),
                "contact_mxid": contact.mxid,
                "contact_display_name": contact.displayName,
                "contact_invite_settings_start": contact.inviteSettings.start,
                "contact_invite_settings_end": contact.inviteSettings.end,
            },
            desc="famedly_invite_checker_add_contact",
        )

    async def get_contact(self, user: UserID, mxid: str) -> Contact | None:
        await self.ensure_table_exists()
        contact = await self.db_pool.simple_select_one(
            "famedly_invite_checker",
            keyvalues={"user": user.to_string(), "contact_mxid": mxid},
            retcols=(
                "contact_display_name",
                "contact_mxid",
                "contact_invite_settings_start",
                "contact_invite_settings_end",
            ),
            desc="famedly_invite_checker_get_contact",
            allow_none=True,
        )
        if contact:
            (name, mxid, start, end) = contact
            return Contact(
                displayName=name,
                mxid=mxid,
                inviteSettings=InviteSettings(start=start, end=end),
            )
        return None
