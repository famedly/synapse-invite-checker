from parameterized import parameterized_class
from synapse.server import HomeServer
from synapse.storage.database import make_conn
from synapse.util import Clock
from twisted.internet.testing import MemoryReactor

from synapse_invite_checker.store import InviteCheckerStore
from synapse_invite_checker.types import Contact, InviteSettings
from tests.base import ModuleApiTestCase


@parameterized_class([{"use_table": True}, {"use_table": False}])
class InviteStoreTests(ModuleApiTestCase):
    """
    Test having and not having the table doesn't stop the world
    """

    use_table = False

    def prepare(self, reactor: MemoryReactor, clock: Clock, homeserver: HomeServer):
        super().prepare(reactor, clock, homeserver)
        api = homeserver.get_module_api()

        dbconfig = None
        for dbconf in api._store.config.database.databases:
            if dbconf.name == "master":
                dbconfig = dbconf

        if not dbconfig:
            msg = "missing database config"
            raise Exception(msg)

        with make_conn(
            dbconfig, api._store.database_engine, "invite_checker_startup"
        ) as db_conn:
            self.store = InviteCheckerStore(api._store.db_pool, db_conn, api._hs)

        self.user_a = self.register_user("a", "password")

        self.contact = Contact(
            displayName="Bob",
            mxid="@bob:fakeserver.com",
            inviteSettings=InviteSettings(start=0, end=None),
        )
        self.contact_mxid = self.contact.mxid

    def test_add_and_get_and_del_contact(self) -> None:
        """
        Specifically for a single contact
        """
        if self.use_table:
            self.get_success(self.store.ensure_table_exists())

        # check contact entry does not exist
        self.assertEqual(
            self.get_success(self.store.get_contact(self.user_a, self.contact_mxid)),
            None,
            "Contact should not be present",
        )

        # Try to add the contact
        self.get_success(self.store.add_contact(self.user_a, self.contact))

        # check contact might be present depending on db_exists
        self.assertEqual(
            self.get_success(self.store.get_contact(self.user_a, self.contact_mxid)),
            self.contact if self.use_table else None,
            "Contact might be present",
        )

        # Try and delete contact
        self.get_success(self.store.del_contact(self.user_a, self.contact_mxid))

        # check contact definitely is gone
        self.assertEqual(
            self.get_success(self.store.get_contact(self.user_a, self.contact_mxid)),
            None,
            "Contact is not present",
        )

    def test_get_and_del_contacts(self) -> None:
        """
        Specifically for multiple contacts
        """
        if self.use_table:
            self.get_success(self.store.ensure_table_exists())

        # Try and get contacts, should be none
        stuff = self.get_success(self.store.get_contacts(self.user_a))
        self.assertEquals(stuff, None)

        # create a few contacts
        contacts_list = [
            ("Alice", "@alice:example.com", 0, None),
            ("Bob", "@bob:fake.com", 0, 400),
            ("Charlie", "@charlie:example.com", 0, None),
        ]
        control_contacts = list(
            [
                Contact(
                    displayName=name,
                    mxid=mxid,
                    inviteSettings=InviteSettings(start=start, end=end),
                )
                for (name, mxid, start, end) in contacts_list
            ]
        )
        # add them
        for contact in control_contacts:
            self.get_success(self.store.add_contact(self.user_a, contact))

        # get them, results vary
        result_contacts = self.get_success(self.store.get_contacts(self.user_a))
        assert result_contacts is None if not self.use_table else True
        if self.use_table:
            self.assertEqual(result_contacts.contacts, control_contacts)
        else:
            self.assertIs(result_contacts, None)

        # drop them
        self.get_success(self.store.del_contacts(self.user_a))

        # get them again, no results
        stuff = self.get_success(self.store.get_contacts(self.user_a))
        self.assertEquals(stuff, None)

    def test_table_exists_and_drop(self) -> None:
        self.assertEquals(
            self.get_success_or_raise(self.store.table_exists(True)),
            False,
            "Table should not exist at beginning",
        )
        if self.use_table:
            self.get_success_or_raise(self.store.ensure_table_exists())

        self.assertEquals(
            self.get_success_or_raise(self.store.table_exists(True)),
            True if self.use_table else False,
            self.use_table,
        )

        self.get_success_or_raise(self.store.drop_table())
        self.assertEquals(
            self.get_success_or_raise(self.store.table_exists(True)),
            False,
            "Table should not exist at end",
        )
