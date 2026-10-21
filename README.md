# ocs — OpenChamber Cloud Shell sync

Restart Google Cloud Shell from a terminal and get the same OpenChamber setup
back, without re-pairing the Android app every time.

`ocs` stores encrypted snapshots in a **private** GitHub repo. The public repo
only contains this code. A passphrase kept at `~/.config/ocs/passphrase`
(mode `600`) decrypts the snapshots; it is never uploaded.

## What is backed up

- OpenChamber settings, preferences, themes, notification settings, project list
- OpenCode sessions/messages (`opencode.db`, copied with SQLite's backup API)
- OpenCode config, auth, shell snapshots
- GitHub CLI auth (per Google account)
- Relay identity and paired-device tokens (per Google account)
- APNs push tokens (per Google account)
- Git config, `.ssh`, `.git-credentials`, `.npmrc`
- Project remotes and branches, so clean repos can be cloned again

Not backed up: project working trees, uncommitted changes, logs, runtime PIDs,
`node_modules`, and the passphrase itself. This is intentional: the snapshot
stays small and restore does not overwrite newer local work.

## Quick start on the current machine

```bash
curl -fsSL https://raw.githubusercontent.com/Protegee1505/openchamber-cloudshell/main/install.sh | bash
ocs init
```

`ocs init` creates the private snapshot repo if needed, generates a random
passphrase if you do not already have one, and uploads the first encrypted
snapshot. **Run `ocs passphrase show` now and store the value in your password
manager.** Losing it makes every snapshot unrecoverable.

## After a Cloud Shell restart

From a local Linux/macOS terminal with `gcloud` installed, install only the
controller CLI (no OpenChamber needed locally):

```bash
OCS_INSTALL_DEPS=0 bash -c "$(curl -fsSL https://raw.githubusercontent.com/Protegee1505/openchamber-cloudshell/main/install.sh)"
ocs local open --account my-google-config
```

Or from inside a fresh Cloud Shell:

```bash
curl -fsSL https://raw.githubusercontent.com/Protegee1505/openchamber-cloudshell/main/install.sh | bash
ocs up
```

`ocs up` restores the latest snapshot only when local OpenChamber data is
missing. On a machine that already has data it just starts OpenChamber, so it
never silently overwrites newer sessions.

The Android app reconnects automatically after restore because
`relay-identity.json` and `remote-clients.json` come back with the snapshot.

## Phone-only pairing (no QR scanner)

Run:

```bash
ocs connect
```

It prints a one-time `openchamber://connect?...` URL. Copy that URL, open
OpenChamber on the phone, choose **Settings → Remote Instances → Import link**,
and paste it. Add `--qr` only when a second screen is available. `--open` tries
`termux-open-url`/`xdg-open` when the terminal supports it.

Each URL is single-use and expires; generate a new one with `ocs connect`.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `ocs up` | Restore if needed, start OpenChamber, show paired clients |
| `ocs save` | Encrypt and upload a snapshot now |
| `ocs restore` | Restore the latest snapshot (or `--snapshot TIMESTAMP`) |
| `ocs reload` | Restart OpenChamber only, without rebooting |
| `ocs connect` | Print a URL for the Android app |
| `ocs status` | Account, server, relay, clients, latest snapshot |
| `ocs doctor` | Check dependencies, auth, DB integrity, hooks, disk |
| `ocs apk` | Latest Android APK URL; `--download` saves it |
| `ocs restart` | Save, then reboot this Cloud Shell VM (asks first) |
| `ocs passphrase show` | Show the cached passphrase (keep it secret) |

## Multiple Google accounts

Use one gcloud configuration per Google account:

```bash
gcloud config configurations create work
gcloud auth login
gcloud config configurations activate work
ocs local accounts
```

The snapshot names include a hash of the active Google account. Restoring uses
the same hash, so a work shell gets the work GitHub auth and relay identity, and
a personal shell gets the personal one. The shared OpenChamber/OpenCode state
is common; only account-specific auth and relay files differ.

On a fresh Google account, open an interactive shell once (`ocs local shell`)
and bootstrap it. The snapshot repo is private, so sign in to GitHub first if
needed (`gh auth login`), then:

```bash
curl -fsSL https://raw.githubusercontent.com/Protegee1505/openchamber-cloudshell/main/install.sh | bash
ocs restore
```

The passphrase is not stored in the snapshot: enter the same one you saved when
prompted (`ocs passphrase set` caches it for later restores). Then `ocs connect`
to pair the phone. After that, `ocs local open` is enough; the passphrase is
cached in that account's home.

## Safety and limits

- Snapshots are encrypted with GPG symmetric AES-256 before upload.
- The last 5 snapshots are kept; older release assets are pruned.
- A pre-restore local archive is written to
  `~/.local/share/ocs/backups/` before state is replaced. It is local,
  unencrypted, and never uploaded; delete it when you no longer need it.
- Temporary build/decrypt trees are removed on success and failure.
- Cloud Shell is not an always-on server. The free VM stops after idle time and
  has a 12-hour maximum; use `ocs local open` to bring it back.
- Do not put the passphrase in the repository, shell history, or a public
  gist. `ocs init` writes it to a `600` file and excludes that file from uploads.
- Release assets are only as private as the private sync repo. Keep that repo
  private and protect the GitHub account with 2FA.

## Requirements

Google Cloud Shell already has most of this. On a fresh image `ocs install
--deps` can install Node 24, OpenCode `2.0.32`, and OpenChamber `2.5.0`.

Required: `bash`, `git`, `curl`, `gpg`, `python3`, `gh` (authenticated), `tar`.
Optional: `gcloud` on the local controlling machine, `qrcode-terminal` for
`ocs connect --qr` (installed with OpenChamber).

## Layout

```
bin/ocs                 main CLI
lib/ocs_helper.py       stdlib-only JSON/SQLite migration helpers
install.sh              bootstrap from the public repo
~/.config/ocs/config    non-secret settings (sync repo, port, retention)
~/.config/ocs/passphrase  local-only encryption key (600)
~/.local/share/ocs/     build/download/backup state
```

## Troubleshooting

```bash
ocs doctor
ocs logs
openchamber status --json
```

- **Wrong passphrase**: `ocs passphrase show` must match the passphrase used when
  the snapshot was encrypted.
- **Refresh the mobile connection**: `ocs connect`, then paste the new URL into
  the app. This is needed after clearing app data or pairing a new phone.
- **Restore did not bring a project back**: only clean git repos with an
  `origin` remote are cloned. Copy uncommitted work manually.
- **GitHub auth missing on a fresh account**: `gh auth login`, then retry.
