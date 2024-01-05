# Synapse Invite Checker

[![PyPI - Version](https://img.shields.io/pypi/v/synapse-invite-checker.svg)](https://pypi.org/project/synapse-invite-checker)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/synapse-invite-checker.svg)](https://pypi.org/project/synapse-invite-checker)

Synapse Invite Policies is a synapse module to restrict invites on a homeserver. Currently this only supports restricting all outgoing invites.

---

**Table of Contents**

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [License](#license)

## Installation

**TODO**: requires publishing on pypi.

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
