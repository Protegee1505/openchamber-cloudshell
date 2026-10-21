#!/usr/bin/env bash
# Bootstrap ocs in a fresh Google Cloud Shell (or any Linux machine).
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Protegee1505/openchamber-cloudshell/main/install.sh)"
#
# The public repo has no secrets. Your snapshots are stored in a separate
# private repo and encrypted before upload.
set -Eeuo pipefail
IFS=$'\n\t'

REPO="${OCS_CODE_REPO:-Protegee1505/openchamber-cloudshell}"
DEST="${OCS_SOURCE_DIR:-$HOME/.local/share/ocs/src}"

say()  { printf '%s\n' "$*"; }
warn() { printf '! %s\n' "$*" >&2; }
die()  { printf 'x %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required."
mkdir -p "$(dirname "$DEST")" "$HOME/.local/bin"

if [[ -d "$DEST/.git" ]]; then
  say "Updating ocs source in $DEST..."
  git -C "$DEST" pull --ff-only >/dev/null 2>&1 || warn "Could not update source; using the existing checkout."
elif [[ -e "$DEST" ]]; then
  die "$DEST exists but is not a git checkout; move it away and retry."
else
  say "Cloning $REPO..."
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh repo clone "$REPO" "$DEST" -- --depth 1 >/dev/null
  else
    git clone --depth 1 "https://github.com/$REPO.git" "$DEST" >/dev/null
  fi
fi

[[ -x "$DEST/bin/ocs" ]] || die "Checkout is missing bin/ocs."

# On the first run, copy the source into the persistent state directory too, so
# the CLI keeps working if this checkout is removed. A laptop that only runs
# `ocs local ...` can skip the OpenChamber dependencies:
#   OCS_INSTALL_DEPS=0 bash -c "$(curl .../install.sh)"
if [[ "${OCS_INSTALL_DEPS:-1}" == "0" ]]; then
  "$DEST/bin/ocs" install --no-deps
else
  "$DEST/bin/ocs" install --deps
fi

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) say ""; say "Add this to your current shell:"; say "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

say ""
say "Installed. Next:"
say "  ocs init      # on a machine that already has OpenChamber data (creates the first snapshot)"
say "  ocs up        # on a fresh Cloud Shell (restores the latest snapshot and starts OpenChamber)"
say "  ocs connect   # print a pairing URL for the Android app"
