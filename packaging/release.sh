#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REPO="VeyloraLabs/VeyloraDevice"

command -v gh >/dev/null || { echo "Install the GitHub CLI (https://cli.github.com) and run 'gh auth login' first." >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/app/__init__.py")"
OUT="$HERE/compilation/Linux-$(uname -m)"
[ -d "$OUT" ] || { echo "Nothing to publish: run ./build.sh first." >&2; exit 1; }

NOTES_FILE="${1:-}"
if [ -z "$NOTES_FILE" ]; then
    NOTES_FILE="$(mktemp)"
    cat >"$NOTES_FILE" <<NOTES

Pick the file for your distribution:

| File | Distributions |
|------|---------------|
| \`.deb\` | Debian, Ubuntu, Linux Mint, Pop!_OS |
| \`.rpm\` | Fedora, openSUSE, RHEL, Rocky, Alma |
| \`.AppImage\` | Any distribution (make it executable and run it) |
| \`.tar.gz\` | Portable, any distribution |

Check the download with \`SHA256SUMS\`.
NOTES
fi

cd "$ROOT"
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null || git tag -a "v$VERSION" -m "VeyloraDevice $VERSION"
git push origin HEAD "v$VERSION"
gh release create "v$VERSION" "$OUT"/* --repo "$REPO" --title "VeyloraDevice $VERSION" --notes-file "$NOTES_FILE"
