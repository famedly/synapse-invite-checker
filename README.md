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
- [Code Quality](#code-quality)
- [Engineering Standards](#engineering-standards)
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
        federation_list_client_cert: "tests/certs/client.pem", # path to a pem encoded client certificate for mtls, required if federation list url is https and federation_list_require_mtls is true
        federation_list_require_mtls: true or false, # Whether to require mTLS for HTTPS federation list URLs. Defaults to true for backwards compatibility
        gematik_ca_baseurl: "https://download-ref.tsl.ti-dienste.de/", # the baseurl to the ca to use for the federation list, required
        tim-type: "epa" or "pro", # Patient/Insurance or Professional mode, defaults to "pro" mode. Optional currently, but will be required in a later release
        tim_version: "1.1" or "1.2", # The TIM specification version to enforce. Defaults to "1.1"
        redaction_max_age: see 'Duration Parsing' below, # Maximum age of an event that can still be redacted by non-admin users. Only enforced when tim_version is "1.2" or above. Defaults to "24h"
        default_permissions: # see 'default_permissions' below. The server defaults for new users or existing users with no permissions already set. Other than the noted default for 'defaultSetting', no other defaults are established
          defaultSetting: "allow all" or "block all" # Default "allow all"
          serverExceptions:
            "<server_name>": # The server names to include. Note the ':' on the end and that double quotes are needed around server names
            "@LOCAL_SERVER@": # A special option to template the local server into without having to know its name. Note that the double quotes are required for this special case.
          userExceptions:
            "<mxid>": # Any users that should be an exception to the 'defaultSetting'.
            "@user:some_server.com": # An example. Note the ':' on the end and that double quotes are needed around user names
          groupException:
          - groupName: "isInsuredPerson" # For the moment, the only option. Note the double quotes and the hyphen at the start of the line
        allowed_room_versions: # The list(as strings) of allowed room versions. Currently optional, defaults are listed
          - "9"
          - "10"
        room_scan_run_interval: see 'Duration Parsing' below, # How often to scan for rooms that are eligible for deletion. Defaults to "1h". Setting to "0" completely disables all room scanning
        insured_only_room_scan:
          enabled: true or false  # optional switch to disable the insured-only room scan from running. The scan is enabled by default, but only runs in EPA mode, otherwise this option is ignored and the scan is disabled.
          grace_period: see 'Duration Parsing' below, # Length of time a room with only EPA members is allowed to exist before deletion. Ignored if `enabled` is false. Defaults to "1w"
          invites_grace_period: see 'Duration Parsing' below, # Optional, a separate grace period just for invites, after which an invite will be considered stale and ignored. Otherwise invited "Pro" users are considered joined and will prevent purging the room. Ignored if `enabled` is false. Defaults to "0", which will never consider an invite stale.
        inactive_room_scan:  # This section only applies to TIM version 1.1. If using a different TIM version, these settings will be ignored
          enabled: true or false # optional switch to disable the room scan for inactive rooms, defaults to true if TIM version is set to "1.1"
          grace_period: see 'Duration Parsing' below # Length of time a room is allowed to have no message activity before it is eligible for deletion. Ignored if 'enabled' is false. Defaults to "26w" which is 6 months
        state_only_room_purge:  # This section only applies to TIM version 1.2. If using an older TIM version, these settings will be ignored
          enabled: true or false  # optional switch to disable the room scan for state only rooms, defaults to true if TIM version is set to "1.2" (or newer)
          grace_period: see 'Duration Parsing' below #  Length of time a room is allowed to have no non-state/timeline activity(such as a message) before it is eligible for deletion. Ignored if 'enabled' is false. Defaults to "6w" which is 6 weeks
        override_public_room_federation: true or false, # Forces the `m.federate` flag to be set to False when creating a public room to prevent it from federating. Default is "true", disable with "false"
        prohibit_world_readable_rooms: true or false, # Prevent setting any rooms history visibility as 'world_readable'. Defaults to "false"
        block_invites_into_dms: true or false, # Prevent invites into existing DM chats. Defaults to true
        limit_reactions: true or false, # Prevent more than a single grapheme cluster in a reaction. Defaults to true, false to disable
        disable_epa_communication: true or false, # Explicitly block all invites and joins to/from ePA domains. Logs a warning at startup when enabled. Defaults to false
```

### default_permissions

For establishing the default permissions for the users on this server. As the simplest
example:

```yaml
default_permissions:
  defaultSetting: "allow all"
```

This is what the default will be if no setting is entered for this section.

an example to allow all communication except for insured users

```yaml
default_permissions:
  defaultSetting: "allow all"
  groupException:
    - groupName: "isInsuredPerson"
```

and an example of blocking all communication except for users on the local server

```yaml
default_permissions:
  defaultSetting: "block all"
  serverExceptions:
    "@LOCAL_SERVER@":
```

### Duration Parsing

Settings labeled as 'duration_parsing' allow for a string representation of the value
that is converted to milliseconds. Suffixes with 's', 'm', 'h', 'd', 'w', or 'y' may be used. For example:
`1h` would translate to `3600000` milliseconds

## Testing

To create virtual env and install dependency:

```console
hatch shell
```

The tests uses pytest, with the development environment managed by hatch. Running the tests can be done like this:

```console
hatch test
```

#### Additional optional testing arguments:

Run the tests in parallel: `-p`

Collect coverage data(automatically output as `lcov.info`): `-c`

#### Running a specific test:

Selecting a specific test to run can be as easy as providing the path to the test. All tests start from
the base test directory, `tests`. If running all tests, this can be left out. If requiring only tests
from `test_createrooms_local.py`, append `tests/test_createrooms_local.py` to the command, and all tests
in that file will run. If requiring only tests in `LocalProModeCreateRoomTest`, appending
`tests/test_createrooms_local.py::LocalProModeCreateRoomTest` to the command will run only those tests.
As an example of running only the test for checking that the default state of the history visibility for a room is "invited":

```console
hatch test tests/test_createrooms_local.py::LocalProModeCreateRoomTest::test_create_room_default_history_visibility_invited
```

## Code Quality

Use `hatch fmt` to automatically format code, enforce style rules, and check types using:

- `black` and `isort` for formatting
- `ruff` for linting
- `mypy` for static type checking

### Check Code Without Modifying It

To check code quality without modifying files:

- Check formatting with `isort` and `black`:
  ```console
  hatch fmt --check -f
  ```
- Check types and linting with `mypy` and `ruff`:
  ```console
  hatch fmt --check -l
  ```
- Check all of above, formatting, linting, and typing:
  ```console
  hatch fmt --check
  ```

### Auto-formatting Code

To automatically fix issues in the code:

- Format only using `black` and `isort`:
  ```console
  hatch fmt -f
  ```
- Type checks(`mypy`) and lint, fixing autofixable `ruff` issues:
  ```console
  hatch fmt -l
  ```
- Run all tools, format, lint, type-check:
  ```console
  hatch fmt
  ```

## Engineering Standards

This repository uses the Famedly
[engineering standards](https://github.com/famedly/engineering-standards). They are
pulled in as a Nix flake input in `flake.nix` and pinned in `flake.lock`. The standards
provide the shared development tooling: a `nix develop` shell, pre-commit hooks run by
`prek`, formatters run by `treefmt`, license checks run by `reuse`, and the CI workflow
that runs the same hooks on every pull request.

Python itself is not managed by Nix. Hatch creates the virtual environments and installs
the Python dependencies with uv, as described under [Testing](#testing) and
[Code Quality](#code-quality). The standards shell supplies the tools around that:
`prek`, `treefmt`, `typos`, `reuse`, and `nix fmt`.

### Setup

1. Install [Lix](https://lix.systems/install/). Any Nix with flakes enabled also works.
2. Enter the shell from the repository root:

   ```console
   nix develop
   ```

   The shell prints a menu of the available commands on entry.

3. Optional: use [direnv](https://direnv.net/) to load the shell automatically when you
   `cd` into the repository.

### Pre-commit hooks

Hooks are run by `prek` and defined in `.pre-commit-config.yaml`. That file is generated
from the standards; see [Generated files](#generated-files) below. The hooks check for
large files, merge conflicts, private keys, broken symlinks, mixed line endings, and
valid JSON, TOML, and XML. They also run `typos`, `treefmt`, `reuse lint-file`, and a
check that flake inputs are de-duplicated.

Useful commands, all available from the shell menu:

- `prek` runs the hooks on the staged changes. It stashes unstaged changes before
  running, so hooks see the staged or committed version of a file.
- `prek --stage pre-push` also runs the slower pre-push hooks.
- `prek -s main -o HEAD` runs the hooks on all commits in the current branch.
- `prek run --all-files` runs the hooks on the whole repository.

CI runs `prek --all-files --stage pre-push` in the standards shell on every pull request
via `.github/workflows/check-pre-commit-hooks.yml`.

### Formatting

`treefmt` formats files that are not covered by `hatch fmt`: Nix (`nixfmt`), Markdown and
YAML (`prettier`), TOML (`taplo`), and shell scripts (`shfmt`). Run it with:

```console
nix fmt
```

Python formatting stays with `hatch fmt`.

### Spelling

`typos` runs with `--write-changes`, so it rewrites what it considers a misspelling. To
keep an intentional spelling, add it under a `[tool.typos]` section in `pyproject.toml`,
for example:

```toml
[tool.typos.default.extend-words]
# Project term, not a misspelling
hassle = "hassle"
```

Per-line opt-outs need a regex in `[tool.typos.default] extend-ignore-re`; see the
[typos reference](https://github.com/crate-ci/typos/blob/master/docs/reference.md).

### Licensing

Every file needs a copyright and license declaration, checked by `reuse`. Famedly code in
this repository is `AGPL-3.0-only`. Files generated by the standards carry an
`Apache-2.0` header; leave those headers as they are.

- Source files take a header comment:

  ```python
  # SPDX-FileCopyrightText: 2026 Famedly GmbH
  #
  # SPDX-License-Identifier: AGPL-3.0-only
  ```

  `reuse annotate --copyright="Famedly GmbH" --license="AGPL-3.0-only" <file>` adds it.

- Files that should not be edited are listed in `REUSE.toml` instead.
- Binary or generated files can take a sidecar `<file>.license` next to them.

`reuse lint` checks the whole repository. License texts live in `LICENSES/`.

### Generated files

The following files are generated from the standards and marked
`managed-by: engineering-standards`. Do not edit them by hand; a `filegen` pre-push hook
fails if they are out of date.

- `.pre-commit-config.yaml`
- `.github/workflows/check-pre-commit-hooks.yml`
- `.editorconfig`
- `.gitattributes`
- `.prettierrc.yaml`
- `.taplo.toml`
- `treefmt.toml`

Repository-specific settings go in `flake.nix`. For example, the pre-commit hooks skip
the test client certificate through
`prek-pre-commit.workspaces.".".exclude` there. After changing `flake.nix`, regenerate
the managed files:

```console
nix run .#filegen-activate
```

### Updating the standards

```console
nix flake update famedly-engineering-standards
nix run .#filegen-activate
```

Commit the resulting changes to `flake.lock` and the generated files together.

## License

`synapse-invite-checker` is distributed under the terms of the
[AGPL-3.0](https://spdx.org/licenses/AGPL-3.0-only.html) license.
