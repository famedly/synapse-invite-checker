# Changelog

All notable changes to this project will be documented in this file.

## [0.4.1] - 2025-03-26

This release now allows system administrators to set default permissions for users. The
permission for allowing all communication is enabled by default(per previous release),
and is automatically set during login. The general prohibition for communication between
EPA mode users is not affected. Look for `default_permissions` in the README.md file for
more information

EPA mode servers will no longer directly purge rooms when kicking users after all PRO
mode users have left, allowing read-only access. Inactive rooms, however, are still
purged by default after 6 months.

Also allow disabling the check for DM when inviting other users to a room by setting
`block_invites_into_dms` to False. By default this is True.

- chore: Allow to disable the DM check for invites (Jason Little)
- chore: Only kick insured users from their rooms, do not purge (Jason Little)
- chore: Refactor `m.room.join_rules` and `m.room.history_visibility` handling for a broader pattern (Jason Little)
- feat: default permissions model for new/existing users (Jason Little)
- fix: Adjust defaultPermissions to be the snake case default_permissions (Jason Little)
- fix: Correct debug message (Jason Little)

## [0.4.0] - 2025-03-17

This release now also enforces permission checks for local users. To offset the
UX impact from that the module defaults to "allow all" in permission checks. The
old contacts API is removed because it is redundant now. The localization checks
are removed for the same reason and because they are not part of the new TIM
specs.

Additionally invites to and from public rooms for remote users are now blocked.
To do that public rooms are now forced during room creation to not federate.
This behaviour can be disabled by setting `override_public_room_federation` to
`false`.

- feat: apply permissions locally (Nicolas Werner)
- feat: Forbid local users from joining remote rooms without an invite (Jason Little)
- feat: Forbid public room federation by forcing `m.federate` to False (Jason Little)
- fix: Silence startup warning for room scan being disabled on incorrect Synapse worker (Jason Little)
- chore: Forbid local users being invited to remote public rooms (Jason Little)
- chore: Forbid local users from sending remote users an invite to a local public room (Jason Little)
- chore: Only enable the Contact Rest API when in PRO server mode (Jason Little)
- chore: Refactor several tests to include some edge cases that were missed and some house cleaning (Jason Little)

## [0.3.1] - 2025-02-25

- fix publishing via github releases

## [0.3.0] - 2025-02-25

This release contains various changes for the upcoming TIM ePA and Pro versions.
Many of these changes are potentially BREAKING changes. Please read the
change log carefully.

### Config changes

- The `api_prefix` config option is removed.
- You can now configure the `tim-type` to `epa` or `pro`. This defaults to `pro`
  for backwards compatibility.
- You can now limit the allowed room versions. This defaults to "9" and "10"
  currently. Please make sure the default room version of synapse matches one of
  the allowed room versions.
- New configuration options for the automatic background jobs for inactive rooms
  and rooms with only insurance users.

### Behaviour changes

- The old contacts API is deprecated. Clients should instead use the account
  data event to change contact rules. For a limited time period this API is
  still available in `pro` mode and tries to stay compatible, but all data is
  migrated to the new account data events, so the displayname of users might be
  missing. Additionally the API will be blocked, when any incompatible changes
  are made to the account data (like setting the default to "allow all").
- Only specific room versions are now allowed when creating a room (or upgrading
  a room).
- Rooms with no activity in the last 6 months will get automatically deleted.
  The time period can be configured.
- Rooms with only insurance users in them will get deleted 1 week after no
  non-insurance user is in the room. This time period can be configured.
- When creating a room a maximum of one invite is allowed.
- Insurance servers can't create public rooms.
- Some of those limitations do not apply to admins.
- Every API requires authentication, even the info endpoints.
- The `/tim-information` API is now available (in `pro` mode).

### Detailed changes

- feat!: Block multiple invites in `createRoom` (Jason Little)
- feat!: Migrate Contacts REST Api to the new Permissions ClientConfig model (Jason Little)
- feat: Add a new endpoint for discovering a server name from ik number (Jason Little)
- feat: Check room version requested when creating a new room (Jason Little)
- feat: Check room version requested when upgrading a room (Jason Little)
- feat: Ensure rooms with only EPA members can be shutdown and purged (Jason Little)
- feat: Forbid insured servers from creating public rooms (Jason Little)
- feat: New `tim-type` configuration setting to enable `epa` or `pro` backend modes. Defaults to `pro` (Jason Little)
- feat: Purge rooms with no activity (Jason Little)
- chore: Add .idea directory to .gitignore for JetBrains IDEs (Jason Little)
- chore: Add a few tests to check exceptions for fed list values (Jason Little)
- chore: Add matrix team to CODEOWNERS (Nicolas Werner)
- chore: Add test for server notice rooms (Jason Little)
- chore: Move the `/tim-information` endpoint from our namespaced area closer to the root (Jason Little)
- chore: Update(and add) metadata versions for various schema (Jason Little)
- ci: Enable code coverage (Emelie Graven)
- ci: properly write coverage files in CI (Nicolas Werner)
- fix: Isolate contact migration to the background tasks worker (Jason Little)
- fix: Only Enable TIM-Information endpoints on PRO mode (Jason Little)
- fix: Relax restrictions for system admins on creating and upgrading rooms (Jason Little)
- refactor: Split unit tests into separate files (Jason Little)
- test: Verify newer Federation List schema is supported and test parsing of its data. (Jason Little)

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
