# SPDX-FileCopyrightText: 2026 Famedly GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: F401
# Ignore imported but unused error to resolve circular imports
from synapse.server import HomeServer

from synapse_invite_checker import InviteChecker
