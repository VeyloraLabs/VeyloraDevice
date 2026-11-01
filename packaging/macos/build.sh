#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$PACK/.." && pwd)"
VERSION_FILE="$ROOT/app/__init__.py"
APP_NAME="VeyloraDevice"
BUNDLE_ID="com.veyloralabs.veyloradevice"

ASSUME_YES=0
NEW_VERSION=""
TARGETS="dmg,zip"
WITH_TOOLS=1

usage() {
    cat <<USAGE
Usage: ./macos/build.sh [options]   (or ./build.sh from the packaging folder)

Builds ${APP_NAME} for macOS and writes the packages to packaging/compilation/macOS-<arch>/

Options:
  -v, --version X.Y.Z   Version to build (skips the prompt)
  -y, --yes             Do not ask anything: keep the current version
  -t, --targets LIST    Comma separated: dmg,zip (default: both)
      --no-tools        Do not bundle the Android platform-tools (adb, fastboot)
  -h, --help            Show this help

Without options the script asks for the version, showing the current one
in brackets: press Enter to keep it or type a new one. The chosen version is
written to app/__init__.py, so the program itself shows it.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        -v|--version) NEW_VERSION="${2:-}"; shift 2 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        -t|--targets) TARGETS="${2:-}"; shift 2 ;;
        --no-tools) WITH_TOOLS=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

log() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$*" >&2; }
has_target() { case ",$TARGETS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

CURRENT_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$VERSION_FILE")"
[ -n "$CURRENT_VERSION" ] || { echo "Could not read __version__ from $VERSION_FILE" >&2; exit 1; }

if [ -z "$NEW_VERSION" ]; then
    if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then
        NEW_VERSION="$CURRENT_VERSION"
    else
        echo "Current version: $CURRENT_VERSION"
        read -r -p "Version to build [$CURRENT_VERSION]: " NEW_VERSION
        NEW_VERSION="${NEW_VERSION:-$CURRENT_VERSION}"
    fi
fi

NEW_VERSION="${NEW_VERSION#v}"
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid version '$NEW_VERSION'. Use the form MAJOR.MINOR.PATCH (for example 1.2.0)." >&2
    exit 1
fi

if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    sed "s/^__version__ = \".*\"$/__version__ = \"$NEW_VERSION\"/" "$VERSION_FILE" >"$VERSION_FILE.tmp"
    mv "$VERSION_FILE.tmp" "$VERSION_FILE"
    log "Version updated: $CURRENT_VERSION -> $NEW_VERSION (written to app/__init__.py)"
else
    log "Building version $NEW_VERSION"
fi
VERSION="$NEW_VERSION"

case "$(uname -m)" in
    arm64|aarch64) MACHINE="arm64" ;;
    x86_64) MACHINE="x86_64" ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

OUT="$PACK/compilation/macOS-$MACHINE"
WORK="$PACK/.work-macos"
VENV="$PACK/.venv-macos"
DIST="$WORK/dist"
APP="$DIST/$APP_NAME.app"

rm -rf "$WORK" "$OUT"
mkdir -p "$OUT" "$WORK"

log "Preparing the Python environment"
command -v python3 >/dev/null || { echo "python3 is required (brew install python)" >&2; exit 1; }
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r "$ROOT/requirements.txt" pyinstaller

log "Compiling $APP_NAME $VERSION with PyInstaller"
EXCLUDES=()
for module in PySide6.QtWebEngineCore PySide6.QtWebEngineWidgets PySide6.QtWebEngineQuick PySide6.QtWebChannel \
    PySide6.Qt3DCore PySide6.Qt3DRender PySide6.Qt3DInput PySide6.Qt3DLogic PySide6.Qt3DAnimation PySide6.Qt3DExtras \
    PySide6.QtQuick PySide6.QtQuickWidgets PySide6.QtQuick3D PySide6.QtQml PySide6.QtCharts PySide6.QtDataVisualization \
    PySide6.QtMultimedia PySide6.QtMultimediaWidgets PySide6.QtSql PySide6.QtTest PySide6.QtBluetooth PySide6.QtNfc \
    PySide6.QtSensors PySide6.QtSerialPort PySide6.QtPositioning PySide6.QtLocation PySide6.QtRemoteObjects \
    PySide6.QtScxml PySide6.QtStateMachine PySide6.QtTextToSpeech PySide6.QtVirtualKeyboard PySide6.QtHttpServer \
    PySide6.QtPdf PySide6.QtPdfWidgets PySide6.QtDesigner PySide6.QtHelp PySide6.QtUiTools PySide6.QtOpenGL \
    PySide6.QtOpenGLWidgets PySide6.QtSpatialAudio PySide6.QtGraphs PySide6.QtGraphsWidgets tkinter scipy numpy matplotlib; do
    EXCLUDES+=(--exclude-module "$module")
done

pyinstaller --noconfirm --clean --windowed --name "$APP_NAME" \
    --icon "$ROOT/assets/icon.icns" --osx-bundle-identifier "$BUNDLE_ID" \
    --distpath "$DIST" --workpath "$WORK/build" --specpath "$WORK" \
    --add-data "$ROOT/assets:assets" \
    --collect-data qfluentwidgets --collect-data qtawesome \
    --hidden-import qtawesome --hidden-import darkdetect \
    "${EXCLUDES[@]}" \
    "$ROOT/main.py" >"$WORK/pyinstaller.log" 2>&1 || { tail -n 40 "$WORK/pyinstaller.log" >&2; exit 1; }

[ -d "$APP" ] || { echo "PyInstaller did not produce $APP" >&2; exit 1; }

PLIST="$APP/Contents/Info.plist"
PLISTBUDDY="/usr/libexec/PlistBuddy"
plist_set() {
    "$PLISTBUDDY" -c "Set :$1 $2" "$PLIST" 2>/dev/null || "$PLISTBUDDY" -c "Add :$1 string $2" "$PLIST"
}
plist_set CFBundleShortVersionString "$VERSION"
plist_set CFBundleVersion "$VERSION"
plist_set LSMinimumSystemVersion "11.0"
plist_set NSHumanReadableCopyright "Copyright 2026 VeyloraLabs. GPL-3.0"

if [ "$WITH_TOOLS" -eq 1 ]; then
    log "Bundling the Android platform-tools (adb, fastboot)"
    if curl -fsSL -o "$WORK/platform-tools.zip" "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"; then
        unzip -q "$WORK/platform-tools.zip" -d "$WORK/tools-src"
        mkdir -p "$APP/Contents/Resources/tools"
        cp -R "$WORK/tools-src/platform-tools" "$APP/Contents/Resources/tools/platform-tools"
    else
        warn "Could not download the platform-tools: the app will look for adb in your PATH"
    fi
fi

log "Signing the app ad hoc (no Apple Developer certificate)"
codesign --force --deep --sign - "$APP"

BASE="$APP_NAME-$VERSION-macos-$MACHINE"

if has_target zip; then
    log "Building the .zip"
    ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/$BASE.zip"
fi

if has_target dmg; then
    log "Building the .dmg"
    STAGE="$WORK/dmg"
    mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create -volname "$APP_NAME $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$OUT/$BASE.dmg" >/dev/null
fi

log "Writing checksums"
(cd "$OUT" && shasum -a 256 -- * >SHA256SUMS)

rm -rf "$WORK"

log "Done. Packages for $APP_NAME $VERSION:"
ls -lh "$OUT" | sed 's/^/    /'
echo
echo "Output folder: $OUT"
echo "Note: the app is not notarized. On first launch: right-click -> Open (or run: xattr -dr com.apple.quarantine /Applications/$APP_NAME.app)"
