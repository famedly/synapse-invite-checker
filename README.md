# Synapse Invite Checker

[![PyPI - Version](https://img.shields.io/pypi/v/synapse-invite-checker.svg)](https://pypi.org/project/synapse-invite-checker)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/synapse-invite-checker.svg)](https://pypi.org/project/synapse-invite-checker)

Synapse Invite Checker is a synapse module to restrict invites on a homeserver according to the rules required by Gematik in a TIM federation.

---

**Table of Contents**

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [License](#license)

## Installation

```console
pip install synapse-invite-checker
```

## Configuration

Here are the available configuration options:

```yaml
# the outer modules section is just provided for completeness, the config block is the actual module config.
modules:
  - module: "synapse_invite_checker.InviteChecker"
    config:
        title: "TIM Contact API by Famedly", # Title for the info endpoint, optional
        description: "Custom description for the endpoint", # Description for the info endpoint, optional
        contact: "random@example.com", # Contact information for the info endpoint, optional
        federation_list_url: "https://localhost:8080", # Full url where to fetch the federation list from, required
        federation_list_client_cert: "tests/certs/client.pem", # path to a pem encoded client certificate for mtls, required if federation list url is https
        gematik_ca_baseurl: "https://download-ref.tsl.ti-dienste.de/", # the baseurl to the ca to use for the federation list, required
        tim-type: "epa" or "pro", # Patient/Insurance or Professional mode, defaults to "pro" mode. Optional currently, but will be required in a later release
        allowed_room_versions: # The list(as strings) of allowed room versions. Currently optional, defaults are listed
          - "9"
          - "10"
        room_scan_run_interval: see 'Duration Parsing' below, # How often to scan for rooms that are eligible for deletion. Defaults to "1h". Setting to "0" completely disables all room scanning
        insured_only_room_scan:
          enabled: true or false  # optional switch to disable the insured-only room scan from running.  The scan is enabled by default, but only runs in EPA mode, otherwise this option is ignored and the scan is disabled.
          grace_period: see 'Duration Parsing' below, # Length of time a room with only EPA members is allowed to exist before deletion. Ignored if `enabled` is false. Defaults to "1w"
        inactive_room_scan:
          enabled: true or false # optional switch to disable the room scan for inactive rooms, defaults to true
          grace_period: see 'Duration Parsing' below # Length of time a room is allowed to have no message activity before it is eligible for deletion. Ignored if 'enabled' is false. Defaults to "26w" which is 6 months
        override_public_room_federation: true or false, # Forces the `m.federate` flag to be set to False when creating a public room to prevent it from federating. Default is "true", disable with "false"
```

### Duration Parsing

Settings labeled as 'duration_parsing' allow for a string representation of the value
that is converted to milliseconds. Suffixes with 's', 'm', 'h', 'd', 'w', or 'y' may be used. For example:
`1h` would translate to `3600000` milliseconds

## Testing

The tests uses twisted's testing framework trial, with the development
enviroment managed by hatch. Running the tests and generating a coverage report
can be done like this:

```console
hatch run cov
```

## License

`synapse-invite-checker` is distributed under the terms of the
[AGPL-3.0](https://spdx.org/licenses/AGPL-3.0-only.html) license.
