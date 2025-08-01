# Copyright 2018-2021 The Matrix.org Foundation C.I.C.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import hashlib
import ipaddress
import json
import logging
import os
import os.path
import sqlite3
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Iterable, MutableMapping, Sequence
from io import SEEK_END, BytesIO
from typing import Any, TypeVar, Union, cast
from unittest.mock import Mock

import attr
import twisted
from incremental import Version
from synapse.config.database import DatabaseConnectionConfig
from synapse.config.homeserver import HomeServerConfig
from synapse.events.presence_router import load_legacy_presence_router
from synapse.handlers.auth import load_legacy_password_auth_providers
from synapse.http.site import SynapseRequest
from synapse.logging.context import ContextResourceUsage
from synapse.module_api.callbacks.spamchecker_callbacks import load_legacy_spam_checkers
from synapse.module_api.callbacks.third_party_event_rules_callbacks import (
    load_legacy_third_party_event_rules,
)
from synapse.server import HomeServer
from synapse.storage import DataStore
from synapse.storage.database import LoggingDatabaseConnection, make_pool
from synapse.storage.engines import BaseDatabaseEngine, create_engine
from synapse.storage.prepare_database import prepare_database
from synapse.types import ISynapseReactor, JsonDict
from synapse.util import Clock
from twisted.enterprise import adbapi
from twisted.internet import address, tcp, threads, udp
from twisted.internet._resolver import SimpleResolverComplexifier
from twisted.internet.defer import Deferred, fail, maybeDeferred, succeed
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import (
    IAddress,
    IConnector,
    IConsumer,
    IHostnameResolver,
    IListeningPort,
    IProducer,
    IProtocol,
    IPullProducer,
    IPushProducer,
    IReactorPluggableNameResolver,
    IReactorTime,
    IResolverSimple,
    ITransport,
)
from twisted.internet.protocol import ClientFactory, DatagramProtocol, Factory
from twisted.internet.testing import AccumulatingProtocol, MemoryReactorClock
from twisted.python import threadpool
from twisted.python.failure import Failure
from twisted.web.http_headers import Headers
from twisted.web.resource import IResource
from twisted.web.server import Request, Site
from typing_extensions import ParamSpec
from zope.interface import implementer

from tests.utils import (
    POSTGRES_BASE_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    SQLITE_PERSIST_DB,
    USE_POSTGRES_FOR_TESTS,
    MockClock,
    default_config,
)

logger = logging.getLogger(__name__)

R = TypeVar("R")
P = ParamSpec("P")

# the type of thing that can be passed into `make_request` in the headers list
CustomHeaderType = tuple[str | bytes, str | bytes]

# A pre-prepared SQLite DB that is used as a template when creating new SQLite
# DB each test run. This dramatically speeds up test set up when using SQLite.
PREPPED_SQLITE_DB_CONN: LoggingDatabaseConnection | None = None


class TimedOutError(Exception):
    """
    A web query timed out.
    """


@implementer(ITransport, IPushProducer, IConsumer)
@attr.s(auto_attribs=True)
class FakeChannel:
    """
    A fake Twisted Web Channel (the part that interfaces with the
    wire).

    See twisted.web.http.HTTPChannel.
    """

    site: Union[Site, "FakeSite"]
    _reactor: MemoryReactorClock
    result: dict = attr.Factory(dict)
    _ip: str = "127.0.0.1"
    _producer: IPullProducer | IPushProducer | None = None
    resource_usage: ContextResourceUsage | None = None
    _request: Request | None = None

    @property
    def request(self) -> Request:
        assert self._request is not None
        return self._request

    @request.setter
    def request(self, request: Request) -> None:
        assert self._request is None
        self._request = request

    @property
    def json_body(self) -> JsonDict:
        body = json.loads(self.text_body)
        assert isinstance(body, dict)
        return body

    @property
    def json_list(self) -> list[JsonDict]:
        body = json.loads(self.text_body)
        assert isinstance(body, list)
        return body

    @property
    def text_body(self) -> str:
        """The body of the result, utf-8-decoded.

        Raises an exception if the request has not yet completed.
        """
        if not self.is_finished():
            msg = "Request not yet completed"
            raise Exception(msg)
        return self.result["body"].decode("utf8")

    def is_finished(self) -> bool:
        """check if the response has been completely received"""
        return self.result.get("done", False)

    @property
    def code(self) -> int:
        if not self.result:
            msg = "No result yet."
            raise Exception(msg)
        return int(self.result["code"])

    @property
    def headers(self) -> Headers:
        if not self.result:
            msg = "No result yet."
            raise Exception(msg)
        h = Headers()
        for i in self.result["headers"]:
            h.addRawHeader(*i)
        return h

    def writeHeaders(
        self, version: bytes, code: bytes, reason: bytes, headers: Headers
    ) -> None:
        self.result["version"] = version
        self.result["code"] = code
        self.result["reason"] = reason
        self.result["headers"] = headers

    def write(self, data: bytes) -> None:
        assert isinstance(data, bytes), "Should be bytes! " + repr(data)

        if "body" not in self.result:
            self.result["body"] = b""

        self.result["body"] += data

    def writeSequence(self, data: Iterable[bytes]) -> None:
        for x in data:
            self.write(x)

    def loseConnection(self) -> None:
        self.unregisterProducer()
        self.transport.loseConnection()

    # Type ignore: mypy doesn't like the fact that producer isn't an IProducer.
    def registerProducer(self, producer: IProducer, streaming: bool) -> None:
        # TODO: This should ensure that the IProducer is an IPushProducer or
        # IPullProducer, unfortunately twisted.protocols.basic.FileSender does
        # implement those, but doesn't declare it.
        self._producer = cast(IPushProducer | IPullProducer, producer)
        self.producerStreaming = streaming

        def _produce() -> None:
            if self._producer:
                self._producer.resumeProducing()
                self._reactor.callLater(0.1, _produce)

        if not streaming:
            self._reactor.callLater(0.0, _produce)

    def unregisterProducer(self) -> None:
        if self._producer is None:
            return

        self._producer = None

    def stopProducing(self) -> None:
        if self._producer is not None:
            self._producer.stopProducing()

    def pauseProducing(self) -> None:
        raise NotImplementedError

    def resumeProducing(self) -> None:
        raise NotImplementedError

    def requestDone(self, _self: Request) -> None:
        self.result["done"] = True
        if isinstance(_self, SynapseRequest):
            assert _self.logcontext is not None
            self.resource_usage = _self.logcontext.get_resource_usage()

    def getPeer(self) -> IAddress:
        # We give an address so that getClientAddress/getClientIP returns a non null entry,
        # causing us to record the MAU
        return cast(IAddress, address.IPv4Address("TCP", self._ip, 3423))

    def getHost(self) -> IAddress:
        # this is called by Request.__init__ to configure Request.host.
        return cast(IAddress, address.IPv4Address("TCP", "127.0.0.1", 8888))

    def isSecure(self) -> bool:
        return False

    @property
    def transport(self) -> "FakeChannel":
        return self

    def await_result(self, timeout_ms: int = 1000) -> None:
        """
        Wait until the request is finished.
        """
        end_time = self._reactor.seconds() + timeout_ms / 1000.0
        self._reactor.run()

        while not self.is_finished():
            # If there's a producer, tell it to resume producing so we get content
            if self._producer:
                self._producer.resumeProducing()

            if self._reactor.seconds() > end_time:
                msg = "Timed out waiting for request to finish."
                raise TimedOutError(msg)

            self._reactor.advance(0.1)

    def extract_cookies(self, cookies: MutableMapping[str, str]) -> None:
        """Process the contents of any Set-Cookie headers in the response

        Any cookines found are added to the given dict
        """
        headers = self.headers.getRawHeaders("Set-Cookie")
        if not headers:
            return

        for h in headers:
            parts = h.split(";")
            k, v = parts[0].split("=", maxsplit=1)
            cookies[k] = v


class FakeSite:
    """
    A fake Twisted Web Site, with mocks of the extra things that
    Synapse adds.
    """

    server_version_string = b"1"
    site_tag = "test"
    access_logger = logging.getLogger("synapse.access.http.fake")

    def __init__(
        self,
        resource: IResource,
        reactor: IReactorTime,
        experimental_cors_msc3886: bool = False,
    ):
        """

        Args:
            resource: the resource to be used for rendering all requests
        """
        self._resource = resource
        self.reactor = reactor
        self.experimental_cors_msc3886 = experimental_cors_msc3886

    def getResourceFor(self, _request: Request) -> IResource:
        return self._resource


def make_request(
    reactor: MemoryReactorClock,
    site: Site | FakeSite,
    method: bytes | str,
    path: bytes | str,
    content: bytes | str | JsonDict = b"",
    access_token: str | None = None,
    request: type[Request] = SynapseRequest,
    shorthand: bool = True,
    federation_auth_origin: bytes | None = None,
    content_is_form: bool = False,
    await_result: bool = True,
    custom_headers: Iterable[CustomHeaderType] | None = None,
    client_ip: str = "127.0.0.1",
) -> FakeChannel:
    """
    Make a web request using the given method, path and content, and render it

    Returns the fake Channel object which records the response to the request.

    Args:
        reactor:
        site: The twisted Site to use to render the request
        method: The HTTP request method ("verb").
        path: The HTTP path, suitably URL encoded (e.g. escaped UTF-8 & spaces and such).
        content: The body of the request. JSON-encoded, if a str of bytes.
        access_token: The access token to add as authorization for the request.
        request: The request class to create.
        shorthand: Whether to try and be helpful and prefix the given URL
            with the usual REST API path, if it doesn't contain it.
        federation_auth_origin: if set to not-None, we will add a fake
            Authorization header pretenting to be the given server name.
        content_is_form: Whether the content is URL encoded form data. Adds the
            'Content-Type': 'application/x-www-form-urlencoded' header.
        await_result: whether to wait for the request to complete rendering. If true,
             will pump the reactor until the the renderer tells the channel the request
             is finished.
        custom_headers: (name, value) pairs to add as request headers
        client_ip: The IP to use as the requesting IP. Useful for testing
            ratelimiting.

    Returns:
        channel
    """
    if not isinstance(method, bytes):
        method = method.encode("ascii")

    if not isinstance(path, bytes):
        path = path.encode("ascii")

    # Decorate it to be the full path, if we're using shorthand
    if (
        shorthand
        and not path.startswith(b"/_matrix")
        and not path.startswith(b"/_synapse")
    ):
        if path.startswith(b"/"):
            path = path[1:]
        path = b"/_matrix/client/r0/" + path

    if not path.startswith(b"/"):
        path = b"/" + path

    if isinstance(content, dict):
        content = json.dumps(content).encode("utf8")
    if isinstance(content, str):
        content = content.encode("utf8")

    channel = FakeChannel(site, reactor, ip=client_ip)  # type: ignore[call-arg]

    req = request(channel, site)
    channel.request = req

    req.content = BytesIO(content)  # type: ignore[assignment]
    # Twisted expects to be at the end of the content when parsing the request.
    req.content.seek(0, SEEK_END)  # type: ignore[attr-defined]

    # Old version of Twisted (<20.3.0) have issues with parsing x-www-form-urlencoded
    # bodies if the Content-Length header is missing
    req.requestHeaders.addRawHeader(
        b"Content-Length", str(len(content)).encode("ascii")
    )

    if access_token:
        req.requestHeaders.addRawHeader(
            b"Authorization", b"Bearer " + access_token.encode("ascii")
        )

    if federation_auth_origin is not None:
        req.requestHeaders.addRawHeader(
            b"Authorization",
            b"X-Matrix origin=%s,key=,sig=" % (federation_auth_origin,),
        )

    if content:
        if content_is_form:
            req.requestHeaders.addRawHeader(
                b"Content-Type", b"application/x-www-form-urlencoded"
            )
        else:
            # Assume the body is JSON
            req.requestHeaders.addRawHeader(b"Content-Type", b"application/json")

    if custom_headers:
        for k, v in custom_headers:
            req.requestHeaders.addRawHeader(k, v)

    req.parseCookies()
    req.requestReceived(method, path, b"1.1")

    if await_result:
        channel.await_result()

    return channel


# ISynapseReactor implies IReactorPluggableNameResolver, but explicitly
# marking this as an implementer of the latter seems to keep mypy-zope happier.
@implementer(IReactorPluggableNameResolver, ISynapseReactor)
class ThreadedMemoryReactorClock(MemoryReactorClock):
    """
    A MemoryReactorClock that supports callFromThread.
    """

    def __init__(self) -> None:
        self.threadpool = ThreadPool(self)

        self._tcp_callbacks: dict[tuple[str, int], Callable] = {}
        self._udp: list[udp.Port] = []
        self.lookups: dict[str, str] = {}
        self._thread_callbacks: deque[Callable[..., R]] = deque()

        lookups = self.lookups

        @implementer(IResolverSimple)
        class FakeResolver:
            def getHostByName(
                self, name: str, _timeout: Sequence[int] | None = None
            ) -> "Deferred[str]":
                if name not in lookups:
                    return fail(DNSLookupError(f"OH NO: unknown {name}"))
                return succeed(lookups[name])

        # In order for the TLS protocol tests to work, modify _get_default_clock
        # on newer Twisted versions to use the test reactor's clock.
        #
        # This is *super* dirty since it is never undone and relies on the next
        # test to overwrite it.
        if twisted.version > Version("Twisted", 23, 8, 0):
            from twisted.protocols import tls

            tls._get_default_clock = lambda: self

        self.nameResolver = SimpleResolverComplexifier(FakeResolver())
        super().__init__()

    def installNameResolver(self, resolver: IHostnameResolver) -> IHostnameResolver:
        raise NotImplementedError

    def listenUDP(
        self,
        port: int,
        protocol: DatagramProtocol,
        interface: str = "",
        maxPacketSize: int = 8196,
    ) -> udp.Port:
        p = udp.Port(port, protocol, interface, maxPacketSize, self)
        p.startListening()
        self._udp.append(p)
        return p

    def callFromThread(
        self,
        # noqa: A002, `callable` is inherited from IReactorFromThreads.callFromThread
        callable: Callable[..., Any],
        *args: object,
        **kwargs: object,
    ) -> None:
        """
        Make the callback fire in the next reactor iteration.
        """

        def cb():
            return callable(*args, **kwargs)

        # it's not safe to call callLater() here, so we append the callback to a
        # separate queue.
        self._thread_callbacks.append(cb)

    def callInThread(
        self,
        # noqa: A002, `callable` is inherited from IReactorFromThreads.callInThread
        callable: Callable[..., Any],
        *args: object,
        **kwargs: object,
    ) -> None:
        raise NotImplementedError

    def suggestThreadPoolSize(self, size: int) -> None:
        raise NotImplementedError

    def getThreadPool(self) -> "threadpool.ThreadPool":
        # Cast to match super-class.
        return cast(threadpool.ThreadPool, self.threadpool)

    def add_tcp_client_callback(
        self, host: str, port: int, callback: Callable[[], None]
    ) -> None:
        """Add a callback that will be invoked when we receive a connection
        attempt to the given IP/port using `connectTCP`.

        Note that the callback gets run before we return the connection to the
        client, which means callbacks cannot block while waiting for writes.
        """
        self._tcp_callbacks[(host, port)] = callback

    def connectUNIX(
        self,
        _address: str,
        _factory: ClientFactory,
        _timeout: float = 30,
        _checkPID: int = 0,
    ) -> IConnector:
        """
        Unix sockets aren't supported for unit tests yet. Make it obvious to any
        developer trying it out that they will need to do some work before being able
        to use it in tests.
        """
        msg = "Unix sockets are not implemented for tests yet, sorry."
        raise Exception(msg)

    def listenUNIX(
        self,
        _address: str,
        _factory: Factory,
        _backlog: int = 50,
        _mode: int = 0o666,
        _wantPID: int = 0,
    ) -> IListeningPort:
        """
        Unix sockets aren't supported for unit tests yet. Make it obvious to any
        developer trying it out that they will need to do some work before being able
        to use it in tests.
        """
        msg = "Unix sockets are not implemented for tests, sorry"
        raise Exception(msg)

    def connectTCP(
        self,
        host: str,
        port: int,
        factory: ClientFactory,
        timeout: float = 30,
        _bindAddress: tuple[str, int] | None = None,
    ) -> IConnector:
        """Fake L{IReactorTCP.connectTCP}."""

        conn = super().connectTCP(
            host, port, factory, timeout=timeout, bindAddress=None
        )
        if self.lookups and host in self.lookups:
            validate_connector(conn, self.lookups[host])

        callback = self._tcp_callbacks.get((host, port))
        if callback:
            callback()

        return conn

    def advance(self, amount: float) -> None:
        # first advance our reactor's time, and run any "callLater" callbacks that
        # makes ready
        super().advance(amount)

        # now run any "callFromThread" callbacks
        while True:
            try:
                callback = self._thread_callbacks.popleft()
            except IndexError:
                break
            callback()

            # check for more "callLater" callbacks added by the thread callback
            # This isn't required in a regular reactor, but it ends up meaning that
            # our database queries can complete in a single call to `advance` [1] which
            # simplifies tests.
            #
            # [1]: we replace the threadpool backing the db connection pool with a
            # mock ThreadPool which doesn't really use threads; but we still use
            # reactor.callFromThread to feed results back from the db functions to the
            # main thread.
            super().advance(0)


def validate_connector(connector: tcp.Connector, expected_ip: str) -> None:
    """Try to validate the obtained connector as it would happen when
    synapse is running and the conection will be established.

    This method will raise a useful exception when necessary, else it will
    just do nothing.

    This is in order to help catch quirks related to reactor.connectTCP,
    since when called directly, the connector's destination will be of type
    IPv4Address, with the hostname as the literal host that was given (which
    could be an IPv6-only host or an IPv6 literal).

    But when called from reactor.connectTCP *through* e.g. an Endpoint, the
    connector's destination will contain the specific IP address with the
    correct network stack class.

    Note that testing code paths that use connectTCP directly should not be
    affected by this check, unless they specifically add a test with a
    matching reactor.lookups[HOSTNAME] = "IPv6Literal", where reactor is of
    type ThreadedMemoryReactorClock.
    For an example of implementing such tests, see test/handlers/send_email.py.
    """
    destination = connector.getDestination()

    # We use address.IPv{4,6}Address to check what the reactor thinks it is
    # is sending but check for validity with ipaddress.IPv{4,6}Address
    # because they fail with IPs on the wrong network stack.
    cls_mapping = {
        address.IPv4Address: ipaddress.IPv4Address,
        address.IPv6Address: ipaddress.IPv6Address,
    }

    cls = cls_mapping.get(destination.__class__)

    if cls is not None:
        try:
            cls(expected_ip)
        except Exception as exc:
            msg = f"Invalid IP type and resolution for {destination}. Expected {expected_ip} to be {cls.__name__}"
            raise ValueError(msg) from exc
    else:
        msg = f"Unknown address type {destination.__class__.__name__} for {destination}"
        raise ValueError(msg)


def make_fake_db_pool(
    reactor: ISynapseReactor,
    db_config: DatabaseConnectionConfig,
    engine: BaseDatabaseEngine,
) -> adbapi.ConnectionPool:
    """Wrapper for `make_pool` which builds a pool which runs db queries synchronously.

    For more deterministic testing, we don't use a regular db connection pool: instead
    we run all db queries synchronously on the test reactor's main thread. This function
    is a drop-in replacement for the normal `make_pool` which builds such a connection
    pool.
    """
    pool = make_pool(reactor, db_config, engine)

    def runWithConnection(
        func: Callable[..., R], *args: Any, **kwargs: Any
    ) -> Awaitable[R]:
        return threads.deferToThreadPool(
            pool._reactor,
            pool.threadpool,
            pool._runWithConnection,
            func,
            *args,
            **kwargs,
        )

    def runInteraction(
        desc: str, func: Callable[..., R], *args: Any, **kwargs: Any
    ) -> Awaitable[R]:
        return threads.deferToThreadPool(
            pool._reactor,
            pool.threadpool,
            pool._runInteraction,
            desc,
            func,
            *args,
            **kwargs,
        )

    pool.runWithConnection = runWithConnection  # type: ignore[method-assign]
    pool.runInteraction = runInteraction  # type: ignore[assignment]
    # Replace the thread pool with a threadless 'thread' pool
    pool.threadpool = ThreadPool(reactor)
    pool.running = True
    return pool


class ThreadPool:
    """
    Threadless thread pool.

    See twisted.python.threadpool.ThreadPool
    """

    def __init__(self, reactor: IReactorTime):
        self._reactor = reactor

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def callInThreadWithCallback(
        self,
        onResult: Callable[[bool, Failure | R], None],
        function: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> "Deferred[None]":
        def _(res: Any) -> None:
            if isinstance(res, Failure):
                onResult(False, res)
            else:
                onResult(True, res)

        d: Deferred[None] = Deferred()
        d.addCallback(lambda _: function(*args, **kwargs))
        d.addBoth(_)
        self._reactor.callLater(0, d.callback, True)
        return d


def _make_test_homeserver_synchronous(server: HomeServer) -> None:
    """
    Make the given test homeserver's database interactions synchronous.
    """

    clock = server.get_clock()

    for database in server.get_datastores().databases:
        pool = database._db_pool

        def wrap_pool(pool):
            def runWithConnection(
                func: Callable[..., R], *args: Any, **kwargs: Any
            ) -> Awaitable[R]:
                return threads.deferToThreadPool(
                    pool._reactor,
                    pool.threadpool,
                    pool._runWithConnection,
                    func,
                    *args,
                    **kwargs,
                )

            def runInteraction(
                desc: str, func: Callable[..., R], *args: Any, **kwargs: Any
            ) -> Awaitable[R]:
                return threads.deferToThreadPool(
                    pool._reactor,
                    pool.threadpool,
                    pool._runInteraction,
                    desc,
                    func,
                    *args,
                    **kwargs,
                )

            pool.runWithConnection = runWithConnection  # type: ignore[method-assign]
            pool.runInteraction = runInteraction  # type: ignore[assignment]
            # Replace the thread pool with a threadless 'thread' pool
            pool.threadpool = ThreadPool(clock._reactor)
            pool.running = True

        wrap_pool(pool)

    # We've just changed the Databases to run DB transactions on the same
    # thread, so we need to disable the dedicated thread behaviour.
    server.get_datastores().main.USE_DEDICATED_DB_THREADS_FOR_EVENT_FETCHING = False


def get_clock() -> tuple[ThreadedMemoryReactorClock, Clock]:
    clock = ThreadedMemoryReactorClock()
    hs_clock = Clock(clock)
    return clock, hs_clock


@implementer(ITransport)
@attr.s(cmp=False, auto_attribs=True)
class FakeTransport:
    """
    A twisted.internet.interfaces.ITransport implementation which sends all its data
    straight into an IProtocol object: it exists to connect two IProtocols together.

    To use it, instantiate it with the receiving IProtocol, and then pass it to the
    sending IProtocol's makeConnection method:

        server = HTTPChannel()
        client.makeConnection(FakeTransport(server, self.reactor))

    If you want bidirectional communication, you'll need two instances.
    """

    other: IProtocol
    """The Protocol object which will receive any data written to this transport.
    """

    _reactor: IReactorTime
    """Test reactor
    """

    _protocol: "IProtocol | None" = None
    """The Protocol which is producing data for this transport. Optional, but if set
    will get called back for connectionLost() notifications etc.
    """

    _peer_address: IAddress = attr.Factory(
        lambda: address.IPv4Address("TCP", "127.0.0.1", 5678)
    )
    """The value to be returned by getPeer"""

    _host_address: IAddress = attr.Factory(
        lambda: address.IPv4Address("TCP", "127.0.0.1", 1234)
    )
    """The value to be returned by getHost"""

    disconnecting = False
    disconnected = False
    connected = True
    buffer: bytes = b""
    producer: IPushProducer | None = None
    autoflush: bool = True

    def getPeer(self) -> IAddress:
        return self._peer_address

    def getHost(self) -> IAddress:
        return self._host_address

    def loseConnection(self) -> None:
        if not self.disconnecting:
            logger.info("FakeTransport: loseConnection()")
            self.disconnecting = True
            if self._protocol:
                self._protocol.connectionLost(
                    Failure(RuntimeError("FakeTransport.loseConnection()"))
                )

            # if we still have data to write, delay until that is done
            if self.buffer:
                logger.info(
                    "FakeTransport: Delaying disconnect until buffer is flushed"
                )
            else:
                self.connected = False
                self.disconnected = True

    def abortConnection(self) -> None:
        logger.info("FakeTransport: abortConnection()")

        if not self.disconnecting:
            self.disconnecting = True
            if self._protocol:
                self._protocol.connectionLost(None)  # type: ignore[arg-type]

        self.disconnected = True

    def pauseProducing(self) -> None:
        if not self.producer:
            return

        self.producer.pauseProducing()

    def resumeProducing(self) -> None:
        if not self.producer:
            return
        self.producer.resumeProducing()

    def unregisterProducer(self) -> None:
        if not self.producer:
            return

        self.producer = None

    def registerProducer(self, producer: IPushProducer, streaming: bool) -> None:
        self.producer = producer
        self.producerStreaming = streaming

        def _produce() -> None:
            if not self.producer:
                # we've been unregistered
                return
            # some implementations of IProducer (for example, FileSender)
            # don't return a deferred.
            d = maybeDeferred(self.producer.resumeProducing)
            d.addCallback(lambda _: self._reactor.callLater(0.1, _produce))

        if not streaming:
            self._reactor.callLater(0.0, _produce)

    def write(self, byt: bytes) -> None:
        if self.disconnecting:
            msg = "Writing to disconnecting FakeTransport"
            raise Exception(msg)

        self.buffer = self.buffer + byt

        # always actually do the write asynchronously. Some protocols (notably the
        # TLSMemoryBIOProtocol) get very confused if a read comes back while they are
        # still doing a write. Doing a callLater here breaks the cycle.
        if self.autoflush:
            self._reactor.callLater(0.0, self.flush)

    def writeSequence(self, seq: Iterable[bytes]) -> None:
        for x in seq:
            self.write(x)

    def flush(self, maxbytes: int | None = None) -> None:
        if not self.buffer:
            # nothing to do. Don't write empty buffers: it upsets the
            # TLSMemoryBIOProtocol
            return

        if self.disconnected:
            return

        to_write = self.buffer[:maxbytes] if maxbytes is not None else self.buffer

        logger.info("%s->%s: %s", self._protocol, self.other, to_write)

        try:
            self.other.dataReceived(to_write)
        except Exception:
            logger.exception("Exception writing to protocol")
            return

        self.buffer = self.buffer[len(to_write) :]
        if self.buffer and self.autoflush:
            self._reactor.callLater(0.0, self.flush)

        if not self.buffer and self.disconnecting:
            logger.info("FakeTransport: Buffer now empty, completing disconnect")
            self.disconnected = True


def connect_client(
    reactor: ThreadedMemoryReactorClock, client_id: int
) -> tuple[IProtocol, AccumulatingProtocol]:
    """
    Connect a client to a fake TCP transport.

    Args:
        reactor
        factory: The connecting factory to build.
    """
    factory = reactor.tcpClients.pop(client_id)[2]
    client = factory.buildProtocol(None)
    server = AccumulatingProtocol()
    server.makeConnection(FakeTransport(client, reactor))  # type: ignore[call-arg]
    client.makeConnection(FakeTransport(server, reactor))  # type: ignore[call-arg]

    return client, server


class TestHomeServer(HomeServer):
    DATASTORE_CLASS = DataStore  # type: ignore[assignment]


def setup_test_homeserver(
    name: str = "test",
    config: HomeServerConfig | None = None,
    reactor: ISynapseReactor | None = None,
    homeserver_to_use: type[HomeServer] = TestHomeServer,
    **kwargs: Any,
) -> HomeServer:
    """
    Setup a homeserver suitable for running tests against.  Keyword arguments
    are passed to the Homeserver constructor.

    If no datastore is supplied, one is created and given to the homeserver.

    Calling this method directly is deprecated: you should instead derive from
    HomeserverTestCase.
    """
    if reactor is None:
        from twisted.internet import reactor as _reactor

        reactor = cast(ISynapseReactor, _reactor)

    if config is None:
        config = default_config(name, parse=True)

    config.caches.resize_all_caches()

    if "clock" not in kwargs:
        kwargs["clock"] = MockClock()

    if USE_POSTGRES_FOR_TESTS:
        test_db = f"synapse_test_{uuid.uuid4().hex}"

        database_config = {
            "name": "psycopg2",
            "args": {
                "dbname": test_db,
                "host": POSTGRES_HOST,
                "password": POSTGRES_PASSWORD,
                "user": POSTGRES_USER,
                "port": POSTGRES_PORT,
                "cp_min": 1,
                "cp_max": 5,
            },
        }
    else:
        if SQLITE_PERSIST_DB:
            # The current working directory is in _trial_temp, so this gets created within that directory.
            test_db_location = os.path.abspath("test.db")
            logger.debug("Will persist db to %s", test_db_location)
            # Ensure each test gets a clean database.
            try:
                os.remove(test_db_location)
            except FileNotFoundError:
                pass
            else:
                logger.debug("Removed existing DB at %s", test_db_location)
        else:
            test_db_location = ":memory:"

        database_config = {
            "name": "sqlite3",
            "args": {"database": test_db_location, "cp_min": 1, "cp_max": 1},
        }

        # Check if we have set up a DB that we can use as a template.
        global PREPPED_SQLITE_DB_CONN
        if PREPPED_SQLITE_DB_CONN is None:
            temp_engine = create_engine(database_config)
            PREPPED_SQLITE_DB_CONN = LoggingDatabaseConnection(
                sqlite3.connect(":memory:"), temp_engine, "PREPPED_CONN"
            )

            database = DatabaseConnectionConfig("master", database_config)
            config.database.databases = [database]
            prepare_database(
                PREPPED_SQLITE_DB_CONN, create_engine(database_config), config
            )

        database_config["_TEST_PREPPED_CONN"] = PREPPED_SQLITE_DB_CONN

    if "db_txn_limit" in kwargs:
        database_config["txn_limit"] = kwargs["db_txn_limit"]

    database = DatabaseConnectionConfig("master", database_config)
    config.database.databases = [database]

    db_engine = create_engine(database.config)

    # Create the database before we actually try and connect to it, based off
    # the template database we generate in setupdb()
    if USE_POSTGRES_FOR_TESTS:
        db_conn = db_engine.module.connect(
            dbname=POSTGRES_BASE_DB,
            user=POSTGRES_USER,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            password=POSTGRES_PASSWORD,
        )
        db_engine.attempt_to_set_autocommit(db_conn, True)
        cur = db_conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {test_db};")
        cur.execute(f"CREATE DATABASE {test_db} WITH TEMPLATE {POSTGRES_BASE_DB};")
        cur.close()
        db_conn.close()

    hs = homeserver_to_use(
        name,
        config=config,
        version_string="Synapse/tests",
        reactor=reactor,
    )

    # Install @cache_in_self attributes
    for key, val in kwargs.items():
        setattr(hs, "_" + key, val)

    # Mock TLS
    hs.tls_server_context_factory = Mock()

    hs.setup()

    # bcrypt is far too slow to be doing in unit tests
    # Need to let the HS build an auth handler and then mess with it
    # because AuthHandler's constructor requires the HS, so we can't make one
    # beforehand and pass it in to the HS's constructor (chicken / egg)
    async def _hash(p: str) -> str:
        return hashlib.md5(p.encode("utf8")).hexdigest()  # noqa: S324

    hs.get_auth_handler().hash = _hash  # type: ignore[assignment]

    async def validate_hash(p: str, h: str) -> bool:
        return hashlib.md5(p.encode("utf8")).hexdigest() == h  # noqa: S324

    hs.get_auth_handler().validate_hash = validate_hash  # type: ignore[assignment]

    # Make the threadpool and database transactions synchronous for testing.
    _make_test_homeserver_synchronous(hs)

    # Load any configured modules into the homeserver
    module_api = hs.get_module_api()
    for module, module_config in hs.config.modules.loaded_modules:
        hs.mockmod = module(config=module_config, api=module_api)  # type: ignore[attr-defined]
        logger.debug("Loaded module %s %r", module, module_config)

    load_legacy_spam_checkers(hs)
    load_legacy_third_party_event_rules(hs)
    load_legacy_presence_router(hs)
    load_legacy_password_auth_providers(hs)

    return hs
