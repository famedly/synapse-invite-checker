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
        api_prefix: "/_synapse/client/test", # Prefix to expose these endpoints under, optional, configure only if you know why you need to change it.
        title: "TIM Contact API by Famedly", # Title for the info endpoint, optional
        description: "Custom description for the endpoint", # Description for the info endpoint, optional
        contact: "random@example.com", # Contact information for the info endpoint, optional
        federation_list_url: "https://localhost:8080", # Full url where to fetch the federation list from, required
        federation_localization_url: "https://localhost:8080/localization", # Full url where to fetch the federation localization from, required. Should be the same host as federation list.
        federation_list_client_cert: "tests/certs/client.pem", # path to a pem encoded client certificate for mtls, required if federation list url is https
        gematik_ca_baseurl: "https://download-ref.tsl.ti-dienste.de/", # the baseurl to the ca to use for the federation list, required
```

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
