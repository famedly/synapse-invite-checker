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
from synapse.storage.engines import PostgresEngine

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
        self.db_exists = False

    async def table_exists(self, force: bool = False) -> bool:
        if not self.db_checked or force:
            # TODO: need to test this, use a hatch matrix
            if isinstance(self.db_pool.engine, PostgresEngine):
                schema_table = "information_schema.tables"
                where_clause = "table_name='famedly_invite_checker_contacts'"
            else:
                schema_table = "sqlite_master"
                where_clause = "type='table' AND name='famedly_invite_checker_contacts'"

            sql = f"SELECT EXISTS (SELECT 1 FROM {schema_table} WHERE {where_clause})"

            result = await self.db_pool.execute(
                "check_invite_checker_table_exists", sql
            )

            self.db_checked = True
            self.db_exists = bool(result[0][0])

        return self.db_exists

    async def ensure_table_exists(self):
        def ensure_table_exists_txn(txn: LoggingTransaction) -> bool:
            sql = """
                CREATE TABLE IF NOT EXISTS famedly_invite_checker_contacts (
                    "owning_user" TEXT NOT NULL,
                    "contact_display_name" TEXT NOT NULL,
                    "contact_mxid" TEXT NOT NULL,
                    "contact_invite_settings_start" BIGINT NOT NULL,
                    "contact_invite_settings_end" BIGINT
                );
                """
            txn.execute(sql)
            txn.execute(
                """
                        CREATE INDEX IF NOT EXISTS famedly_invite_checker_contacts_user
                        ON famedly_invite_checker_contacts("owning_user");
                        """
            )
            txn.execute(
                """
                        CREATE UNIQUE INDEX IF NOT EXISTS famedly_invite_checker_contacts_user_mxid
                        ON famedly_invite_checker_contacts("owning_user", "contact_mxid");
                        """
            )
            return True

        await self.db_pool.runInteraction(
            "ensure_invite_checker_table_exists", ensure_table_exists_txn
        )
        # Just created the table, unilaterally tell the store to recheck it's there
        self.db_checked = False

    async def drop_table(self) -> None:
        if await self.table_exists(force=True):

            def drop(conn: LoggingDatabaseConnection) -> None:
                cur = conn.cursor(txn_name="check_invite_checker_drop_table")
                self.db_pool.engine.executescript(
                    cur, "DROP TABLE IF EXISTS famedly_invite_checker_contacts;"
                )

            await self.db_pool.runWithConnection(drop)

            self.db_checked = False

    async def get_contacts(self, user: str) -> Contacts | None:
        if not await self.table_exists():
            return
        contacts = await self.db_pool.simple_select_list(
            "famedly_invite_checker_contacts",
            keyvalues={"owning_user": user},
            retcols=(
                "contact_display_name",
                "contact_mxid",
                "contact_invite_settings_start",
                "contact_invite_settings_end",
            ),
            desc="famedly_invite_checker_get_contacts",
        )
        return (
            Contacts(
                contacts=[
                    Contact(
                        displayName=name,
                        mxid=mxid,
                        inviteSettings=InviteSettings(start=start, end=end),
                    )
                    for (name, mxid, start, end) in contacts
                ]
            )
            if contacts
            else None
        )

    async def del_contact(self, user: str, contact: str) -> None:
        if not await self.table_exists():
            return
        await self.db_pool.simple_delete(
            "famedly_invite_checker_contacts",
            {"owning_user": user, "contact_mxid": contact},
            desc="famedly_invite_checker_del_contact",
        )

    async def del_contacts(self, user: str) -> None:
        if await self.table_exists():
            await self.db_pool.simple_delete(
                "famedly_invite_checker_contacts",
                {"owning_user": user},
                desc="famedly_invite_checker_del_contacts",
            )

    async def add_contact(self, user: str, contact: Contact) -> None:
        if not await self.table_exists():
            return
        await self.db_pool.simple_upsert(
            "famedly_invite_checker_contacts",
            keyvalues={"owning_user": user, "contact_mxid": contact.mxid},
            values={
                "owning_user": user,
                "contact_mxid": contact.mxid,
                "contact_display_name": contact.displayName,
                "contact_invite_settings_start": contact.inviteSettings.start,
                "contact_invite_settings_end": contact.inviteSettings.end,
            },
            desc="famedly_invite_checker_add_contact",
        )

    async def get_contact(self, user: str, contact_mxid: str) -> Contact | None:
        if not await self.table_exists():
            return None
        contact = await self.db_pool.simple_select_one(
            "famedly_invite_checker_contacts",
            keyvalues={"owning_user": user, "contact_mxid": contact_mxid},
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
            (name, contact_mxid, start, end) = contact
            return Contact(
                displayName=name,
                mxid=contact_mxid,
                inviteSettings=InviteSettings(start=start, end=end),
            )
        return None

    async def get_all_contact_owners_for_migration(self) -> set[str]:
        """
        Retrieves all contact owner rows from the database to begin migration. May be run
        more than once and will just return an empty Set instead of None
        """
        contact_owners: set[str] = set()
        if await self.table_exists():
            # I'm not sure I like how this pulls data duplicatedly
            contact_rows = await self.db_pool.simple_select_list(
                "famedly_invite_checker_contacts",
                keyvalues=None,
                retcols=("owning_user",),
                desc="famedly_invite_checker_store_migration",
            )
            for (owning_user,) in contact_rows:
                logger.debug(f"FOUND OWNING USER: {owning_user}")
                contact_owners.add(owning_user)

        return contact_owners
