# Contributing

This project manages the setup and lifecycle of an unmodified upstream co-op
engine. Keep launcher changes separate from gameplay-engine changes.

## Development

On Windows with Python 3.13 and Tkinter:

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s manager -p test_core.py -v
python scripts/build_release.py
python manager/app.py
```

The first build downloads and verifies the pinned upstream release. The runtime
app needs no third-party Python modules. Tests use synthetic files; they do not
need Fallout 2. Full engine checks require a licensed local installation.

## Expectations for changes

- Preserve the original Steam installation. Keep all runtime writes inside the
  manager's own Play, World, Backups and Logs directories.
- Never bundle proprietary assets, real saves, user settings, access tokens,
  addresses or private logs. The release builder uses an explicit file allowlist.
- Never start an admin listener or automatically broaden firewall/router access.
- Keep blocking file copies and process work off the Tk main thread.
- For backup/restore changes, test failure paths and preservation of the previous
  world, not only the happy path.
- Keep user-facing steps aligned with the actual menus, and make experimental
  limitations clear. Do not imply that a build passing means a campaign passes.
- Run real visible-client engine tests sequentially: the engine permits one
  visible client per computer.
- Update engine hashes, source links, third-party notices and validation evidence
  together if changing the pinned engine version.

Describe the problem, the resulting behavior, and relevant validation in pull
requests. AI assistance is welcome; disclose it and verify the result.
