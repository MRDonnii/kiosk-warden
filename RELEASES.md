# Kiosk Warden release standard

Kiosk Warden uses one monotonically increasing semantic version sequence for
both channels.

- Tags are `vMAJOR.MINOR.PATCH`.
- Stable releases are normal GitHub Releases titled `Kiosk Warden vX.Y.Z`.
- Beta releases are GitHub prereleases titled `Kiosk Warden vX.Y.Z Beta`.
- `VERSION` contains the same version without the leading `v`.
- The newest `CHANGELOG.md` heading matches the tag and release date.
- Published tags are immutable and must never be moved or reused.

The Stable updater uses GitHub's latest stable release endpoint. The Beta
updater uses the newest release, including prereleases. Every installation is
snapshotted locally before files are replaced. Runtime configuration,
credentials, screenshots and user backups are never part of release snapshots
or release archives.

Before publishing:

1. Update `VERSION` and prepend `CHANGELOG.md`.
2. Run `scripts/check-release.sh`.
3. Commit and push the exact release commit.
4. Create the matching immutable tag and GitHub Release.
5. Verify title, tag, prerelease flag, target commit and release notes.
6. Verify Stable and Beta discovery and install the release on a real kiosk.
