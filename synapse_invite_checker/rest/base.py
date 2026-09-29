# SPDX-FileCopyrightText: 2026 Famedly GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only
import re


def invite_checker_pattern(root_prefix: str, path_regex: str):
    path = path_regex.removeprefix("/")
    root = root_prefix.removesuffix("/")
    raw_regex = f"^{root}/{path}"

    # we need to strip the /$, otherwise we can't register for the root of the prefix in a handler...
    if raw_regex.endswith("/$"):
        raw_regex = raw_regex.replace("/$", "$")

    return [re.compile(raw_regex)]
