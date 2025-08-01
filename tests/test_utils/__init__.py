# Copyright 2019-2021 The Matrix.org Foundation C.I.C.
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

"""
Utilities for running the unit tests
"""

import json
import sys
import warnings
from binascii import unhexlify
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, TypeVar

import attr
from synapse.types import JsonSerializable
from twisted.internet.interfaces import IProtocol
from twisted.python.failure import Failure
from twisted.web.client import ResponseDone
from twisted.web.http import RESPONSES
from twisted.web.http_headers import Headers
from twisted.web.iweb import IResponse
from zope.interface import implementer

if TYPE_CHECKING:
    from sys import UnraisableHookArgs

TV = TypeVar("TV")

# Only use this server name for our PRO test instance
SERVER_NAME_FROM_LIST = "tim.test.gematik.de"
# Use a domain found in our raw fedlist data instead of inserting a fake one
DOMAIN_IN_LIST = "timo.staging.famedly.de"
DOMAIN2_IN_LIST = "tim-alpha.staging.famedly.de"
DOMAIN3_IN_LIST = "messenger.spilikin.dev"
# Only use this server name for our EPA test instance
INSURANCE_DOMAIN_IN_LIST = "cirosec.de"
# And another 'isInsurance' domain for testing local
INSURANCE_DOMAIN_IN_LIST_FOR_LOCAL = "ti-messengertest.dev.ccs.gematik.solutions"


def get_awaitable_result(awaitable: Awaitable[TV]) -> TV:
    """Get the result from an Awaitable which should have completed

    Asserts that the given awaitable has a result ready, and returns its value
    """
    i = awaitable.__await__()
    try:
        next(i)
    except StopIteration as e:
        # awaitable returned a result
        return e.value

    # if next didn't raise, the awaitable hasn't completed.
    msg = "awaitable has not yet completed"
    raise Exception(msg)


def setup_awaitable_errors() -> Callable[[], None]:
    """
    Convert warnings from a non-awaited coroutines into errors.
    """
    warnings.simplefilter("error", RuntimeWarning)

    # State shared between unraisablehook and check_for_unraisable_exceptions.
    unraisable_exceptions = []
    orig_unraisablehook = sys.unraisablehook

    def unraisablehook(unraisable: "UnraisableHookArgs") -> None:
        unraisable_exceptions.append(unraisable.exc_value)

    def cleanup() -> None:
        """
        A method to be used as a clean-up that fails a test-case if there are any new unraisable exceptions.
        """
        sys.unraisablehook = orig_unraisablehook
        if unraisable_exceptions:
            exc = unraisable_exceptions.pop()
            assert exc is not None
            raise exc

    sys.unraisablehook = unraisablehook

    return cleanup


class IResponseProto(Protocol):
    def deliverBody(self, protocol: IProtocol) -> None: ...


# Type ignore: it does not fully implement IResponse, but is good enough for tests
@implementer(IResponse)
@attr.s(slots=True, frozen=True, auto_attribs=True)
class FakeResponse:  # type: ignore[misc]
    """A fake twisted.web.IResponse object

    there is a similar class at treq.test.test_response, but it lacks a `phrase`
    attribute, and didn't support deliverBody until recently.
    """

    version: tuple[bytes, int, int] = (b"HTTP", 1, 1)

    # HTTP response code
    code: int = 200

    # body of the response
    body: bytes = b""

    headers: Headers = attr.Factory(Headers)

    @property
    def phrase(self) -> bytes:
        return RESPONSES.get(self.code, b"Unknown Status")

    @property
    def length(self) -> int:
        return len(self.body)

    def deliverBody(self, protocol: IProtocol) -> None:
        protocol.dataReceived(self.body)
        protocol.connectionLost(Failure(ResponseDone()))

    @classmethod
    def json(cls, *, code: int = 200, payload: JsonSerializable) -> "FakeResponse":
        headers = Headers({"Content-Type": ["application/json"]})
        body = json.dumps(payload).encode("utf-8")
        return cls(code=code, body=body, headers=headers)  # type: ignore[call-arg]


# A small image used in some tests.
#
# Resolution: 1x1, MIME type: image/png, Extension: png, Size: 67 B
SMALL_PNG = unhexlify(
    b"89504e470d0a1a0a0000000d4948445200000001000000010806"
    b"0000001f15c4890000000a49444154789c63000100000500010d"
    b"0a2db40000000049454e44ae426082"
)
