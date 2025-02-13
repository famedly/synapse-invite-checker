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
import base64
import functools
import logging
from contextlib import suppress
from typing import Any, Callable, Dict, Literal, cast
from urllib.parse import quote, urlparse

from cachetools import TTLCache, keys
from jwcrypto import jwk, jws
from OpenSSL.crypto import (
    FILETYPE_ASN1,
    FILETYPE_PEM,
    X509,
    X509Store,
    X509StoreContext,
    dump_certificate,
    load_certificate,
)
from synapse.api.constants import AccountDataTypes
from synapse.api.errors import SynapseError
from synapse.api.room_versions import RoomVersion
from synapse.config import ConfigError
from synapse.http.client import BaseHttpClient
from synapse.http.proxyagent import ProxyAgent
from synapse.http.server import JsonResource
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.server import HomeServer
from synapse.storage.database import make_conn
from synapse.types import Requester, UserID
from twisted.internet.defer import Deferred
from twisted.internet.ssl import PrivateCertificate, optionsForClientTLS, platformTrust
from twisted.web.client import HTTPConnectionPool
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface import implementer

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.permissions import (
    InviteCheckerPermissionsHandler,
)
from synapse_invite_checker.rest.contacts import (
    ContactManagementInfoResource,
    ContactResource,
    ContactsResource,
)
from synapse_invite_checker.rest.messenger_info import (
    MessengerInfoResource,
    MessengerIsInsuranceResource,
)

from synapse_invite_checker.store import InviteCheckerStore
from synapse_invite_checker.types import FederationList, TimType


logger = logging.getLogger(__name__)

# We need to access the private API in some places, in particular the store and the homeserver
# ruff: noqa: SLF001


def cached(cache):
    """Simplified cached decorator from cachetools, that allows calling an async function."""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            k = keys.hashkey(*args, **kwargs)
            with suppress(KeyError):
                return cache[k]

            v = await func(*args, **kwargs)

            with suppress(ValueError):
                cache[k] = v

            return v

        def cache_clear():
            cache.clear()

        wrapper.cache = cache
        wrapper.cache_clear = cache_clear

        return functools.update_wrapper(wrapper, func)

    return decorator


@implementer(IPolicyForHTTPS)
class MtlsPolicy:
    def __init__(self, config: InviteCheckerConfig):
        super().__init__()

        self.url = urlparse(config.federation_list_url)

        # if no certificate is specified, we assume the connection uses http and no MTLS
        client_cert = None
        if config.federation_list_client_cert:
            with open(config.federation_list_client_cert) as file:
                content = file.read()

            client_cert = PrivateCertificate.loadPEM(content)
        elif self.url.scheme != "http":
            msg = "No mtls cert and scheme is not http"
            raise Exception(msg)

        self.options = optionsForClientTLS(
            self.url.hostname, platformTrust(), clientCertificate=client_cert
        )

    def creatorForNetloc(self, hostname, port):
        if self.url.hostname != hostname or self.url.port != port:
            msg = "Invalid connection attempt by MTLS Policy"
            raise Exception(msg)
        return self.options


class FederationAllowListClient(BaseHttpClient):
    """Custom http client since we need to pass a custom agent to enable mtls"""

    def __init__(
        self,
        hs: HomeServer,
        config: InviteCheckerConfig,
        # We currently assume the configured endpoint is always trustworthy and bypass the proxy
        # ip_allowlist: Optional[IPSet] = None,
        # ip_blocklist: Optional[IPSet] = None,
        # use_proxy: bool = False,
    ):
        super().__init__(hs)

        pool = HTTPConnectionPool(self.reactor)
        self.agent = ProxyAgent(
            self.reactor,
            hs.get_reactor(),
            connectTimeout=15,
            contextFactory=MtlsPolicy(config),
            pool=pool,
        )


BASE_API_PREFIX = "/_synapse/client/com.famedly/tim"


class InviteChecker:
    __version__ = "0.2.0"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self.api = api

        self.config = config

        self.federation_list_client = FederationAllowListClient(api._hs, self.config)

        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)
        self.api.register_third_party_rules_callbacks(
            on_create_room=self.on_create_room
        )
        self.api.register_third_party_rules_callbacks(
            on_upgrade_room=self.on_upgrade_room
        )

        self.resource = JsonResource(api._hs)

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

        self.permissions_handler = InviteCheckerPermissionsHandler(
            self.api,
            self.fetch_localization_for_mxid,
            self.is_domain_insurance,
        )

        # The Contact Management API resources
        ContactManagementInfoResource(self.config).register(self.resource)
        ContactsResource(self.api, self.store, self.permissions_handler).register(
            self.resource
        )
        ContactResource(self.api, self.store, self.permissions_handler).register(
            self.resource
        )

        # The TiMessengerInformation API resource
        MessengerInfoResource(self.config).register(self.resource)
        MessengerIsInsuranceResource(self.config, self.is_domain_insurance).register(
            self.resource
        )

        # Register everything at the root of our namespace/app, to avoid complicating
        # Synapse's regex http registration
        self.api.register_web_resource(BASE_API_PREFIX, self.resource)

        self.api._hs._reactor.callWhenRunning(self.after_startup)

        logger.info("Module initialized at %s", BASE_API_PREFIX)

    @staticmethod
    def parse_config(config: Dict[str, Any]) -> InviteCheckerConfig:
        logger.error("PARSE CONFIG")
        _config = InviteCheckerConfig()

        _config.title = config.get("title", _config.title)
        _config.description = config.get("description", _config.description)
        _config.contact = config.get("contact", _config.contact)
        _config.federation_list_client_cert = config.get(
            "federation_list_client_cert", ""
        )
        _config.federation_list_url = config.get("federation_list_url", "")
        _config.federation_localization_url = config.get(
            "federation_localization_url", ""
        )
        _config.gematik_ca_baseurl = config.get("gematik_ca_baseurl", "")

        if not _config.federation_list_url or not _config.gematik_ca_baseurl:
            msg = "Incomplete federation list config"
            raise Exception(msg)

        if (
            not _config.federation_localization_url
            or urlparse(_config.federation_list_url).hostname
            != urlparse(_config.federation_localization_url).hostname
            or urlparse(_config.federation_list_url).scheme
            != urlparse(_config.federation_localization_url).scheme
        ):
            msg = "Expected localization url on the same host as federation list"
            raise Exception(msg)

        if (
            _config.federation_list_url.startswith("https")
            and not _config.federation_list_client_cert
        ):
            msg = "Federation list config requires an mtls (PEM) cert for https connections"
            raise Exception(msg)

        # Check that the configuration is defined. This allows a grace period for
        # migration. For now, just issue a warning in the logs. The default of 'pro'
        # is set inside InviteCheckerConfig
        _tim_type = config.get("tim-type", "").lower()
        if not _tim_type:
            logger.warning(
                "Please remember to set `tim-type` in your configuration. Defaulting to 'Pro' mode"
            )

        else:
            if _tim_type == "epa":
                _config.tim_type = TimType.EPA
            elif _tim_type == "pro":
                _config.tim_type = TimType.PRO
            else:
                msg = "`tim-type` setting is not a recognized value. Please fix."
                raise ConfigError(msg)

        _allowed_room_versions = config.get("allowed_room_versions", ["9", "10"])
        if not _allowed_room_versions or not isinstance(_allowed_room_versions, list):
            msg = "Allowed room versions must be formatted as a list."
            raise ConfigError(msg)

        _config.allowed_room_versions = [
            # Coercing into a string, in case the yaml loader thought it was an int
            str(_room_ver)
            for _room_ver in _allowed_room_versions
        ]
        return _config

    def after_startup(self) -> None:
        """
        To be called when the reactor is running. Validates that the epa setting matches
        the insurance setting in the federation list and *might* perform forced contact
        migration.
        """
        fetch_deferred = Deferred.fromCoroutine(self._fetch_federation_list())
        fed_list = cast(FederationList, fetch_deferred.result)
        if self.config.tim_type == TimType.EPA and not fed_list.is_insurance(
            self.api._hs.config.server.server_name
        ):
            logger.warning(
                "This server has enabled ePA Mode in its config, but is not found on "
                "the Federation List as an Insurance Domain!"
            )

        _ = Deferred.fromCoroutine(self.run_migration())

    async def run_migration(self) -> None:
        """
        Migrate Contacts from the database to Account Data in Synapse, one owning user at
        a time. This WILL delete the contacts table after it has completed!

        Safe to run multiple times
        """
        contact_owners = await self.store.get_all_contact_owners_for_migration()
        if not contact_owners:
            logger.warning("No Contacts to migrate. Skipping")
            return

        logger.warning("BEGINNING MASS MIGRATION OF CONTACTS")

        while contact_owners:
            # Recursively process, in the extremely unlikely event that new data was found
            for owner in contact_owners:
                contacts = await self.store.get_contacts(owner)

                permissions = await self.permissions_handler.get_permissions(owner)
                for contact in contacts.contacts:
                    permissions.userExceptions.setdefault(contact.mxid, {})

                await self.permissions_handler.update_permissions(owner, permissions)
                await self.store.del_contacts(owner)

            # This will reset contact_owners and break if there are none
            contact_owners = await self.store.get_all_contact_owners_for_migration()

        logger.warning("FINISHED MASS MIGRATION OF CONTACTS. DROPPING CONTACT TABLE!!")
        await self.store.drop_table()

    async def _raw_localization_fetch(self, mxid: str) -> str:  # pragma: no cover
        resp = await self.federation_list_client.get_raw(
            self.config.federation_localization_url, {"mxid": mxid}
        )
        return resp.decode().strip(
            '"'
        )  # yes, they sometimes are quoted and we don't know what is right yet

    async def fetch_localization_for_mxid(self, mxid: str) -> str:
        """Fetches from the VZD if this mxid is org, pract, orgPract or none.
        Sadly the specification mixes mxids and matrix uris (in incorrect formats) several times,
        which is why we need to try all of the variations for now until we know what is correct.
        """

        with suppress(errors.HttpResponseException):
            # this format matches the matrix spec, but not the gematik documentation...
            matrix_uri = f"matrix:u/{quote(mxid[1:], safe='')}"
            loc = await self._raw_localization_fetch(matrix_uri)
            if loc != "none":
                return loc

        with suppress(errors.HttpResponseException):
            # this format matches the matrix spec apart from not encoding the :
            matrix_uri = f"matrix:u/{quote(mxid[1:], safe=':')}"
            loc = await self._raw_localization_fetch(matrix_uri)
            if loc != "none":
                return loc

        with suppress(errors.HttpResponseException):
            # this format matches the gematik spec, but not the matrix spec for URIs nor the actual practice...
            matrix_uri = f"matrix:user/{quote(mxid[1:], safe='')}"
            loc = await self._raw_localization_fetch(matrix_uri)
            if loc != "none":
                return loc

        with suppress(errors.HttpResponseException):
            # this format matches the gematik spec, but not the matrix spec for URIs nor the actual practice...
            # It also doesn't encode the : since we have seen such entries in the wild...
            matrix_uri = f"matrix:user/{quote(mxid[1:], safe=':')}"
            loc = await self._raw_localization_fetch(matrix_uri)
            if loc != "none":
                return loc

        with suppress(errors.HttpResponseException):
            # The test servers all have written mxids into them instead of matrix uris as required
            loc = await self._raw_localization_fetch(mxid)
            if loc != "none":
                return loc

        return "none"

    async def _raw_federation_list_fetch(self) -> str:
        resp = await self.federation_list_client.get_raw(
            self.config.federation_list_url
        )
        return resp.decode()

    async def _raw_gematik_root_ca_fetch(self) -> dict:
        return await self.api._hs.get_proxied_http_client().get_json(
            f"{self.config.gematik_ca_baseurl}/ECC/ROOT-CA/roots.json"
        )

    async def _raw_gematik_intermediate_cert_fetch(self, cn: str) -> bytes:
        return await self.api._hs.get_proxied_http_client().get_raw(
            f"{self.config.gematik_ca_baseurl}/ECC/SUB-CA/{quote(cn.replace(' ', '_'), safe='')}.der"
        )

    def _load_cert_b64(self, cert: str) -> X509:
        return load_certificate(FILETYPE_ASN1, base64.b64decode(cert))

    @cached(cache=TTLCache(maxsize=1, ttl=60 * 60))
    async def _fetch_federation_list(
        self,
    ) -> FederationList:
        """
        Fetch the raw data for the federation list, verify it is authentic and parse
        the data into a usable format

        Returns:
            a FederationList object

        """
        raw_list = await self._raw_federation_list_fetch()
        jws_verify = jws.JWS()
        jws_verify.deserialize(raw_list, alg="BP256R1")
        jws_verify.allowed_algs = ["BP256R1"]

        jwskey = self._load_cert_b64(jws_verify.jose_header["x5c"][0])

        # TODO(Nico): Fetch the ca only once a week
        store = X509Store()
        roots = await self._raw_gematik_root_ca_fetch()
        for r in roots:
            rawcert = r["cert"]
            if rawcert:
                store.add_cert(self._load_cert_b64(rawcert))

        chain = load_certificate(
            FILETYPE_ASN1,
            await self._raw_gematik_intermediate_cert_fetch(jwskey.get_issuer().CN),
        )
        store_ctx = X509StoreContext(store, jwskey, chain=[chain])
        store_ctx.verify_certificate()

        key = jwk.JWK.from_pem(dump_certificate(FILETYPE_PEM, jwskey))

        jws_verify.verify(key, alg="BP256R1")

        if jws_verify.payload is None:
            msg = "Empty federation list"
            raise Exception(msg)

        # Validate incoming, potentially incomplete or corrupt data
        return FederationList.model_validate_json(jws_verify.payload)

    async def _domain_list_check(self, check: Callable[[str], bool]) -> bool:
        """Run a `check` against data found on the FederationList"""
        fed_list = await self._fetch_federation_list()
        if check(fed_list):
            return True

        # Per A_25537:
        # The domain wasn't found but the list may have changed since the last look.
        # Re-fetch the list and try again. See:
        # https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_Basis/gemSpec_TI-M_Basis_V1.1.1/#A_25537
        self._fetch_federation_list.cache_clear()
        fed_list = await self._fetch_federation_list()
        return check(fed_list)

    async def is_domain_allowed(self, domain: str) -> bool:
        return await self._domain_list_check(lambda fl: fl.allowed(domain))

    async def is_domain_insurance(self, domain: str) -> bool:
        return await self._domain_list_check(lambda fl: fl.is_insurance(domain))

    async def on_upgrade_room(self, _: Requester, room_version: RoomVersion) -> None:
        if room_version.identifier not in self.config.allowed_room_versions:
            raise SynapseError(
                400,
                f"Room version ('{room_version}') not allowed",
                errors.Codes.FORBIDDEN,
            )

    async def on_create_room(
        self,
        requester: Requester,
        request_content: dict[str, Any],
        is_request_admin: bool,
    ) -> None:
        """
        Raise a SynapseError if creating a room should be denied. Currently, this checks
        invites
        room version
        """
        # Unlike `user_may_invite()`, `on_create_room()` only runs with the inviter being
        # a local user and the invitee is remote. Unfortunately, the spam check module
        # function `user_may_create_room()` only accepts the user creating the room and
        # has no other information provided.

        invite_list: list[str] = request_content.get("invite", [])
        # Per A_25538, only a single additional user may be invited to a room during
        # creation. See:
        # https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_Basis/gemSpec_TI-M_Basis_V1.1.1/#A_25538
        # Interesting potential error here, they display an http error code of 400, but
        # then say to use "M_FORBIDDEN". Pretty sure that is a typo
        if len(invite_list) > 1:
            raise SynapseError(
                403,
                "When creating a room, a maximum of one participant can be invited directly",
                errors.Codes.FORBIDDEN,
            )

        inviter = requester.user.to_string()
        for invitee in invite_list:
            res = await self.user_may_invite(inviter, invitee)
            if res != "NOT_SPAM":
                raise SynapseError(
                    403,
                    f"Room not created as user ({invitee}) is not allowed to be invited",
                    errors.Codes.FORBIDDEN,
                )

        # The room version should always be a string to accommodate arbitrary unstable
        # room versions. If it was not explicitly requested, the homeserver defaults
        # will be used. Make sure to check that instance as well
        room_version: str = request_content.get(
            "room_version", self.api._hs.config.server.default_room_version.identifier
        )

        if room_version not in self.config.allowed_room_versions:
            raise SynapseError(
                400,
                f"Room version ('{room_version}') not allowed",
                errors.Codes.FORBIDDEN,
            )

    async def user_may_invite(
        self, inviter: str, invitee: str, room_id: str | None = None
    ) -> Literal["NOT_SPAM"] | errors.Codes:
        # Check local invites first, no need to check federation invites for those
        if self.api.is_mine(inviter):
            if self.config.tim_type == TimType.EPA:
                # The TIM-ePA backend forbids all local invites
                if self.api.is_mine(invitee):
                    return errors.Codes.FORBIDDEN

            # Verify that local users can't invite into their DMs as verified by a few
            # tests in the Testsuite. In the context of calling this directly from
            # `on_create_room()` above, there may not be a room_id yet.
            if room_id:
                direct = await self.api.account_data_manager.get_global(
                    inviter, AccountDataTypes.DIRECT
                )
                if direct:
                    for user, roomids in direct.items():
                        if room_id in roomids and user != invitee:
                            # Can't invite to DM!
                            logger.debug(
                                "Preventing invite since %s already has a DM with %s",
                                inviter,
                                invitee,
                            )
                            return errors.Codes.FORBIDDEN

            # local invites are always valid, if they are not to a dm (and not in EPA mode).
            if self.api.is_mine(invitee):
                logger.debug("Local invite from %s to %s allowed", inviter, invitee)
                return NOT_SPAM

        remote_user_id = inviter if not self.api.is_mine(inviter) else invitee
        remote_domain = UserID.from_string(remote_user_id).domain
        local_user_id = invitee if self.api.is_mine(invitee) else inviter
        local_domain = UserID.from_string(local_user_id).domain

        # Step 1a, check federation allow list. See:
        # https://gemspec.gematik.de/docs/gemSpec/gemSpec_TI-M_Basis/gemSpec_TI-M_Basis_V1.1.1/#A_25534
        if not (
            await self.is_domain_allowed(remote_domain)
            and await self.is_domain_allowed(local_domain)
        ):
            logger.warning(
                "Discarding invite between domains: (%s) and (%s)",
                remote_domain,
                local_domain,
            )
            return errors.Codes.FORBIDDEN

        # Step 1b
        # Per AF_10233: Deny incoming remote invites if in ePA mode(which means the
        # local user is an 'insured') and if the remote domain is type 'insurance'.
        if await self.is_domain_insurance(
            local_domain
        ) and await self.is_domain_insurance(remote_domain):
            logger.warning(
                "Discarding invite from remote insurance domain: %s", remote_domain
            )
            return errors.Codes.FORBIDDEN

        # Step 2, check invite settings
        # Get the local user permissions, because our server doesn't have the remote users
        if await self.permissions_handler.is_user_allowed(
            local_user_id, remote_user_id
        ):
            logger.debug(
                "Allowing invite since local user (%s) allowed the remote user (%s) in their permissions",
                local_user_id,
                remote_user_id,
            )
            return NOT_SPAM

        # Step 3, no active invite settings found, ensure we
        # - either invite an org
        # - or both users are practitioners and the invitee has no restricted visibility
        # The values org, pract, orgPract stand for org membership, practitioner and both respectively.
        invitee_loc = await self.fetch_localization_for_mxid(invitee)
        if invitee_loc in {"orgPract", "org"}:
            logger.debug(
                "Allowing invite since invitee %s is an organization (%s)",
                invitee,
                invitee_loc,
            )
            return NOT_SPAM
        else:
            logger.debug("Invitee %s is not an organization (%s)", invitee, invitee_loc)

        visiblePract = {"pract", "orgPract"}
        inviter_loc = await self.fetch_localization_for_mxid(inviter)
        if invitee_loc in visiblePract and inviter_loc in visiblePract:
            logger.debug(
                "Allowing invite since invitee (%s) and inviter (%s) are both practitioners (%s and %s)",
                invitee,
                inviter,
                invitee_loc,
                inviter_loc,
            )
            return NOT_SPAM

        logger.debug(
            "Not allowing invite since invitee (%s) and inviter (%s) are not both practitioners (%s and %s) and all previous checks failed",
            invitee,
            inviter,
            invitee_loc,
            inviter_loc,
        )

        # Forbid everything else (so remote invites not matching step1, 2 or 3)
        return errors.Codes.FORBIDDEN
