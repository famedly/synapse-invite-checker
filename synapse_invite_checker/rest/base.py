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

CONTACT_MANAGEMENT_API_PREFIX = "/_synapse/client/com.famedly/tim/v1"
INFO_API_PREFIX = "/_synapse/client/com.famedly/tim/v2/tim-information"


def invite_checker_pattern(path_regex: str, root_prefix: str):
    path = path_regex.removeprefix("/")
    root = root_prefix.removesuffix("/")
    raw_regex = f"^{root}/{path}"

    # we need to strip the /$, otherwise we can't register for the root of the prefix in a handler...
    if raw_regex.endswith("/$"):
        raw_regex = raw_regex.replace("/$", "$")

    return [re.compile(raw_regex)]
