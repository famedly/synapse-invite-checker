# Changelog

All notable changes to this project will be documented in this file.

## [0.2.2] - 2025-11-05

- chore: Update publish to PyPI Github Action (Jason Little)

## [0.2.1] - 2025-11-05

- chore: update CI workflow to allow for manual triggering and to stop being selective about pull requests (Jason Little)
- chore: Update matrix-synapse dependency to point at the correct repository (Jason Little)
- chore: update ruff github workflow action to current (Jason Little)
- fix: Adjust some class/function arguments for compatibility with imported objects. For Synapse v1.140.0 (Jason Little)
- fix: Adjust to Synapse utilities that use Metrics and now require a 'server_name' and kwargs. For Synapse v1.136-v1.138 (Jason Little)
- fix codeowners (Jason Little)
- fix: Move where Clock is imported from. For Synapse 1.139.0 (Jason Little)
- update .gitignore for .idea based IDE's (Jason Little)

## [0.2.0] - 2024-05-22

- Use SimpleHttpClient with proxy enabled to fetch CA roots

## [0.0.9] - 2023-02-10

BREAKING: rename user column to avoid issues with SQL statements on postgres (that aren't handled by the synapse DB
API). This also renames the table to simplify migration. You may want to delete the old (and probably empty table).

## [0.0.8] - 2023-02-09

- Deal with quoted strings returned as the localization

## [0.0.7] - 2023-02-08

- Treat both org and orgPract as organization membership
- Treat both pract and orgPract as practitioners
- Allow unencoded colons in matrix URIs (and gematik URIs)
- Add debug logging for invite checks

## [0.0.6] - 2023-02-08

- Allow invites to organization practitioners from any federation member

## [0.0.5] - 2023-01-30

- Ensure the "user" column name is properly quoted on postgres

## [0.0.4] - 2023-01-29

- Properly map CN to SUB-CA certificates

## [0.0.3] - 2023-01-26

- Drop direct dependency on synapse to prevent pip from overwriting the locally installed one

## [0.0.2] - 2023-01-26

- Properly depend on our dependencies instead of only in the hatch environment.

## [0.0.1] - 2023-01-25

### Features

- forked from the invite policies module
