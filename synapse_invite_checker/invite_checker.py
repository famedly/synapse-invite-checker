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
import time
from contextlib import suppress
from typing import Literal
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
from synapse.http.client import BaseHttpClient
from synapse.http.proxyagent import ProxyAgent
from synapse.http.server import JsonResource
from synapse.module_api import NOT_SPAM, ModuleApi, errors
from synapse.server import HomeServer
from synapse.storage.database import make_conn
from synapse.types import UserID
from twisted.internet.ssl import PrivateCertificate, optionsForClientTLS, platformTrust
from twisted.web.client import HTTPConnectionPool
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface import implementer

from synapse_invite_checker.config import InviteCheckerConfig
from synapse_invite_checker.handlers import (
    ContactResource,
    ContactsResource,
    InfoResource,
)
from synapse_invite_checker.store import InviteCheckerStore
from synapse_invite_checker.types import FederationList

logger = logging.getLogger(__name__)

# We need to acces the private API in some places, in particular the store and the homeserver
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


class InviteChecker:
    __version__ = "0.0.5"

    def __init__(self, config: InviteCheckerConfig, api: ModuleApi):
        self.api = api

        self.config = config

        self.federation_list_client = FederationAllowListClient(api._hs, self.config)

        self.api.register_spam_checker_callbacks(user_may_invite=self.user_may_invite)

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

        InfoResource(self.config, self.__version__).register(self.resource)
        ContactsResource(self.api, self.store, self.config).register(self.resource)
        ContactResource(self.api, self.store, self.config).register(self.resource)

        self.api.register_web_resource(f"{config.api_prefix}", self.resource)
        logger.info("Module initialized at %s", config.api_prefix)

    @staticmethod
    def parse_config(config):
        logger.error("PARSE CONFIG")
        _config = InviteCheckerConfig()

        _config.api_prefix = config.get(
            "api_prefix", "/_synapse/client/com.famedly/tim/v1"
        )
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

        return _config

    async def _raw_localization_fetch(self, mxid: str) -> str:
        resp = await self.federation_list_client.get_raw(
            self.config.federation_localization_url, {"mxid": mxid}
        )
        return resp.decode()

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
            # this format matches the gematik spec, but not the matrix spec for URIs nor the actual practice...
            matrix_uri = f"matrix:user/{quote(mxid[1:], safe='')}"
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
        return await self.api.http_client.get_json(
            f"{self.config.gematik_ca_baseurl}/ECC/ROOT-CA/roots.json"
        )

    async def _raw_gematik_intermediate_cert_fetch(self, cn: str) -> bytes:
        return await self.api.http_client.get_raw(
            f"{self.config.gematik_ca_baseurl}/ECC/SUB-CA/{quote(cn.replace(' ', '_'), safe='')}.der"
        )

    def _load_cert_b64(self, cert: str) -> X509:
        return load_certificate(FILETYPE_ASN1, base64.b64decode(cert))

    @cached(cache=TTLCache(maxsize=1, ttl=60 * 60))
    async def fetch_federation_allow_list(self) -> set[str]:
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

        fedlist = FederationList.model_validate_json(jws_verify.payload)
        return {fed.domain for fed in fedlist.domainList}

    async def user_may_invite(
        self, inviter: str, invitee: str, room_id: str
    ) -> Literal["NOT_SPAM"] | errors.Codes:
        # Check local invites first, no need to check federation invites for those
        # This verifies that local users can't invite into their DMs as verified by a few tests in the Testsuite
        if self.api.is_mine(inviter):
            direct = await self.api.account_data_manager.get_global(
                inviter, AccountDataTypes.DIRECT
            )
            if direct:
                for user, roomids in direct.items():
                    if room_id in roomids and user != invitee:
                        # Can't invite to DM!
                        return errors.Codes.FORBIDDEN

            # local invites are always valid, if they are not to a dm.
            # There are no checks done for outgoing invites apart from in the federation proxy,
            # which checks all requests.
            # if self.api.is_mine(invitee):
            return NOT_SPAM

        # Step 1, check federation allow list
        inviter_id = UserID.from_string(inviter)
        inviter_domain = inviter_id.domain
        fedlist = await self.fetch_federation_allow_list()
        if inviter_domain not in fedlist:
            self.fetch_federation_allow_list.cache_clear()
            fedlist = await self.fetch_federation_allow_list()

            if inviter_domain not in fedlist:
                logger.warning("Discarding invite from domain: %s", inviter_domain)
                return errors.Codes.FORBIDDEN

        # Step 2, check invite settings
        contact = await self.store.get_contact(UserID.from_string(invitee), inviter)
        seconds_since_epoch = int(time.time())
        if (
            contact
            and contact.inviteSettings.start <= seconds_since_epoch
            and (
                contact.inviteSettings.end is None
                or contact.inviteSettings.end >= seconds_since_epoch
            )
        ):
            return NOT_SPAM

        # Step 3, no active invite settings found, ensure both users are publicly viewable as pract or orgPract
        visible = ["pract", "orgPract"]
        if (await self.fetch_localization_for_mxid(inviter)) in visible and (
            await self.fetch_localization_for_mxid(invitee)
        ) in visible:
            return NOT_SPAM

        # Forbid everything else (so remote invites not matching step1, 2 or 3)
        return errors.Codes.FORBIDDEN
