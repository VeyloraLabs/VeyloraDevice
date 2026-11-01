#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$(uname -s)" in
    Linux)
        exec "$HERE/linux/build.sh" "$@"
        ;;
    Darwin)
        exec "$HERE/macos/build.sh" "$@"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        SHELL_EXE="$(command -v pwsh || command -v powershell || true)"
        [ -n "$SHELL_EXE" ] || { echo "PowerShell was not found." >&2; exit 1; }
        PS_ARGS=()
        while [ $# -gt 0 ]; do
            case "$1" in
                -v|--version) PS_ARGS+=(-Version "${2:-}"); shift 2 ;;
                -y|--yes) PS_ARGS+=(-Yes); shift ;;
                -t|--targets) PS_ARGS+=(-Targets "${2:-}"); shift 2 ;;
                *) PS_ARGS+=("$1"); shift ;;
            esac
        done
        exec "$SHELL_EXE" -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/windows/build.ps1")" "${PS_ARGS[@]}"
        ;;
    *)
        echo "Unsupported system: $(uname -s)" >&2
        exit 1
        ;;
esac
