#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REPO="VeyloraLabs/VeyloraDevice"

command -v gh >/dev/null || { echo "Install the GitHub CLI (https://cli.github.com) and run 'gh auth login' first." >&2; exit 1; }

VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/app/__init__.py")"
COMPILATION="$HERE/compilation"
ls "$COMPILATION"/*/ >/dev/null 2>&1 || { echo "Nothing to publish: run ./build.sh first." >&2; exit 1; }

UPLOAD="$(mktemp -d)"
for folder in "$COMPILATION"/*/; do
    for file in "$folder"*; do
        [ "$(basename "$file")" = "SHA256SUMS" ] || cp "$file" "$UPLOAD/"
    done
    cat "$folder/SHA256SUMS" >>"$UPLOAD/SHA256SUMS"
done

NOTES_FILE="${1:-}"
if [ -z "$NOTES_FILE" ]; then
    NOTES_FILE="$(mktemp)"
    cat >"$NOTES_FILE" <<NOTES
## VeyloraDevice $VERSION

Pick the file for your system:

| File | System |
|------|--------|
| \`VeyloraDevice-Setup-*-windows-*.exe\` | Windows 10/11 (installer) |
| \`VeyloraDevice-*-windows-*.zip\` | Windows (portable) |
| \`VeyloraDevice-*-macos-arm64.dmg\` | macOS on Apple Silicon (M1 and newer) |
| \`VeyloraDevice-*-macos-x86_64.dmg\` | macOS on Intel |
| \`.deb\` | Debian, Ubuntu, Linux Mint, Pop!_OS |
| \`.rpm\` | Fedora, openSUSE, RHEL, Rocky, Alma |
| \`.AppImage\` | Any Linux distribution (make it executable and run it) |
| \`linux-*.tar.gz\` | Linux, portable |

Check the download with \`SHA256SUMS\`.
NOTES
fi

cd "$ROOT"
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null || git tag -a "v$VERSION" -m "VeyloraDevice $VERSION"
git push origin HEAD "v$VERSION"
gh release create "v$VERSION" "$UPLOAD"/* --repo "$REPO" --title "VeyloraDevice $VERSION" --notes-file "$NOTES_FILE"
