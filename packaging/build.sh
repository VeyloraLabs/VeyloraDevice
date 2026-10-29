#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VERSION_FILE="$ROOT/app/__init__.py"
APP_NAME="VeyloraDevice"
PKG_NAME="veyloradevice"
MAINTAINER="VeyloraLabs <noreply@github.com>"
HOMEPAGE="https://github.com/VeyloraLabs/VeyloraDevice"
SUMMARY="Apple and Android device manager"

ASSUME_YES=0
NEW_VERSION=""
TARGETS="tar,deb,rpm,appimage"

usage() {
    cat <<USAGE
Usage: ./build.sh [options]

Builds ${APP_NAME} for Linux and writes every package to ./compilation/Linux-<arch>/

Options:
  -v, --version X.Y.Z   Version to build (skips the prompt)
  -y, --yes             Do not ask anything: keep the current version
  -t, --targets LIST    Comma separated: tar,deb,rpm,appimage (default: all)
  -h, --help            Show this help

Without options the script shows the current version already typed in the
prompt: press Enter to keep it, or edit it to publish a new one. The chosen
version is written to app/__init__.py, so the program itself shows it.
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        -v|--version) NEW_VERSION="${2:-}"; shift 2 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        -t|--targets) TARGETS="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

log() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$*" >&2; }
has_target() { case ",$TARGETS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

CURRENT_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$VERSION_FILE")"
if [ -z "$CURRENT_VERSION" ]; then
    echo "Could not read __version__ from $VERSION_FILE" >&2
    exit 1
fi

if [ -z "$NEW_VERSION" ]; then
    if [ "$ASSUME_YES" -eq 1 ] || [ ! -t 0 ]; then
        NEW_VERSION="$CURRENT_VERSION"
    else
        echo "Current version: $CURRENT_VERSION"
        read -r -e -i "$CURRENT_VERSION" -p "Version to build: " NEW_VERSION
        NEW_VERSION="${NEW_VERSION:-$CURRENT_VERSION}"
    fi
fi

NEW_VERSION="${NEW_VERSION#v}"
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid version '$NEW_VERSION'. Use the form MAJOR.MINOR.PATCH (for example 1.2.0)." >&2
    exit 1
fi

if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    sed -i "s/^__version__ = \".*\"$/__version__ = \"$NEW_VERSION\"/" "$VERSION_FILE"
    log "Version updated: $CURRENT_VERSION -> $NEW_VERSION (written to app/__init__.py)"
else
    log "Building version $NEW_VERSION"
fi
VERSION="$NEW_VERSION"

MACHINE="$(uname -m)"
case "$MACHINE" in
    x86_64) DEB_ARCH="amd64"; RPM_ARCH="x86_64"; APPIMAGE_ARCH="x86_64" ;;
    aarch64|arm64) MACHINE="aarch64"; DEB_ARCH="arm64"; RPM_ARCH="aarch64"; APPIMAGE_ARCH="aarch64" ;;
    *) echo "Unsupported architecture: $MACHINE" >&2; exit 1 ;;
esac

OUT="$HERE/compilation/Linux-$MACHINE"
WORK="$HERE/.work"
VENV="$HERE/.venv"
DIST="$WORK/dist"
BUNDLE="$DIST/$APP_NAME"

rm -rf "$WORK" "$OUT"
mkdir -p "$OUT" "$WORK"

log "Preparing the Python environment"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
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
    --distpath "$DIST" --workpath "$WORK/build" --specpath "$WORK" \
    --add-data "$ROOT/assets:assets" \
    --collect-data qfluentwidgets --collect-data qtawesome \
    --hidden-import qtawesome --hidden-import darkdetect \
    "${EXCLUDES[@]}" \
    "$ROOT/main.py" >"$WORK/pyinstaller.log" 2>&1 || { tail -n 40 "$WORK/pyinstaller.log" >&2; exit 1; }

[ -x "$BUNDLE/$APP_NAME" ] || { echo "PyInstaller did not produce $BUNDLE/$APP_NAME" >&2; exit 1; }
BUNDLE_SIZE="$(du -sh "$BUNDLE" | cut -f1)"
log "Binary ready ($BUNDLE_SIZE)"

ICON="$ROOT/assets/icon-512.png"
DESKTOP="$HERE/templates/$PKG_NAME.desktop"

stage_root() {
    local root="$1"
    mkdir -p "$root/opt" "$root/usr/bin" "$root/usr/share/applications" \
        "$root/usr/share/icons/hicolor/512x512/apps" "$root/usr/share/doc/$PKG_NAME"
    cp -a "$BUNDLE" "$root/opt/$PKG_NAME"
    ln -s "/opt/$PKG_NAME/$APP_NAME" "$root/usr/bin/$PKG_NAME"
    cp "$DESKTOP" "$root/usr/share/applications/$PKG_NAME.desktop"
    cp "$ICON" "$root/usr/share/icons/hicolor/512x512/apps/$PKG_NAME.png"
    cp "$ROOT/LICENSE" "$root/usr/share/doc/$PKG_NAME/copyright"
    cp "$ROOT/THIRD_PARTY_NOTICES.md" "$root/usr/share/doc/$PKG_NAME/THIRD_PARTY_NOTICES.md"
}

if has_target tar; then
    log "Building the portable .tar.gz"
    TAR_NAME="$APP_NAME-$VERSION-linux-$MACHINE"
    mkdir -p "$WORK/tar/$TAR_NAME"
    cp -a "$BUNDLE/." "$WORK/tar/$TAR_NAME/"
    cp "$ROOT/LICENSE" "$ROOT/README.md" "$ROOT/THIRD_PARTY_NOTICES.md" "$WORK/tar/$TAR_NAME/"
    tar -C "$WORK/tar" -czf "$OUT/$TAR_NAME.tar.gz" "$TAR_NAME"
fi

if has_target deb; then
    if command -v dpkg-deb >/dev/null; then
        log "Building the .deb (Debian, Ubuntu, Linux Mint, Pop!_OS...)"
        DEB_ROOT="$WORK/deb"
        stage_root "$DEB_ROOT"
        mkdir -p "$DEB_ROOT/DEBIAN"
        INSTALLED_SIZE="$(du -sk "$DEB_ROOT" | cut -f1)"
        cat >"$DEB_ROOT/DEBIAN/control" <<CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Installed-Size: $INSTALLED_SIZE
Maintainer: $MAINTAINER
Homepage: $HOMEPAGE
Depends: libc6, libgl1, libxkbcommon-x11-0, libxcb-cursor0
Recommends: libimobiledevice-utils, ideviceinstaller, idevicerestore, usbmuxd, libirecovery-utils, adb | android-tools-adb, fastboot | android-tools-fastboot
Suggests: scrcpy
Description: $SUMMARY
 VeyloraDevice shows device information in real time, manages apps and
 files, takes screenshots, and handles firmware for iPhone, iPad and Android
 devices from one window. Made by VeyloraLabs.
CONTROL
        dpkg-deb --root-owner-group --build "$DEB_ROOT" "$OUT/${PKG_NAME}_${VERSION}_${DEB_ARCH}.deb" >/dev/null
    else
        warn "dpkg-deb not found: skipping the .deb"
    fi
fi

if has_target rpm; then
    if command -v rpmbuild >/dev/null; then
        log "Building the .rpm (Fedora, openSUSE, RHEL, Rocky...)"
        RPM_TOP="$WORK/rpm"
        mkdir -p "$RPM_TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}
        RPM_STAGE="$WORK/rpm-stage"
        stage_root "$RPM_STAGE"
        cat >"$RPM_TOP/SPECS/$PKG_NAME.spec" <<SPEC
Name:           $PKG_NAME
Version:        $VERSION
Release:        1
Summary:        $SUMMARY
License:        GPL-3.0-only
URL:            $HOMEPAGE
BuildArch:      $RPM_ARCH
AutoReqProv:    no
Recommends:     libimobiledevice-utils
Recommends:     ideviceinstaller
Recommends:     idevicerestore
Recommends:     usbmuxd
Recommends:     android-tools
Suggests:       scrcpy

%description
VeyloraDevice shows device information in real time, manages apps and files,
takes screenshots, and handles firmware for iPhone, iPad and Android devices
from one window. Made by VeyloraLabs.

%install
mkdir -p %{buildroot}
cp -a $RPM_STAGE/. %{buildroot}/

%files
/opt/$PKG_NAME
/usr/bin/$PKG_NAME
/usr/share/applications/$PKG_NAME.desktop
/usr/share/icons/hicolor/512x512/apps/$PKG_NAME.png
%doc /usr/share/doc/$PKG_NAME/THIRD_PARTY_NOTICES.md
%license /usr/share/doc/$PKG_NAME/copyright

%changelog
* $(LC_ALL=C date '+%a %b %d %Y') VeyloraLabs <noreply@github.com> - $VERSION-1
- Release $VERSION
SPEC
        rpmbuild -bb --quiet --define "_topdir $RPM_TOP" --define "_build_id_links none" \
            --define "__os_install_post %{nil}" --define "debug_package %{nil}" \
            --target "$RPM_ARCH" "$RPM_TOP/SPECS/$PKG_NAME.spec" >"$WORK/rpmbuild.log" 2>&1 \
            || { tail -n 30 "$WORK/rpmbuild.log" >&2; exit 1; }
        cp "$RPM_TOP"/RPMS/*/*.rpm "$OUT/"
    else
        warn "rpmbuild not found (install the 'rpm' package): skipping the .rpm"
    fi
fi

if has_target appimage; then
    log "Building the AppImage (any distribution)"
    APPDIR="$WORK/$APP_NAME.AppDir"
    mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
    cp -a "$BUNDLE/." "$APPDIR/usr/bin/"
    cp "$DESKTOP" "$APPDIR/$PKG_NAME.desktop"
    cp "$DESKTOP" "$APPDIR/usr/share/applications/$PKG_NAME.desktop"
    cp "$ICON" "$APPDIR/$PKG_NAME.png"
    cp "$ICON" "$APPDIR/usr/share/icons/hicolor/512x512/apps/$PKG_NAME.png"
    cat >"$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/VeyloraDevice" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"
    TOOL="$HERE/.cache/appimagetool-$APPIMAGE_ARCH.AppImage"
    if [ ! -x "$TOOL" ]; then
        mkdir -p "$HERE/.cache"
        if command -v curl >/dev/null && curl -fsSL -o "$TOOL" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$APPIMAGE_ARCH.AppImage"; then
            chmod +x "$TOOL"
        else
            rm -f "$TOOL"
        fi
    fi
    if [ -x "$TOOL" ]; then
        ARCH="$APPIMAGE_ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" \
            "$OUT/$APP_NAME-$VERSION-$APPIMAGE_ARCH.AppImage" >"$WORK/appimage.log" 2>&1 \
            || { warn "appimagetool failed (see $WORK/appimage.log): skipping the AppImage"; }
    else
        warn "Could not download appimagetool: skipping the AppImage"
    fi
fi

log "Writing checksums"
(cd "$OUT" && sha256sum -- * >SHA256SUMS)

rm -rf "$WORK"

log "Done. Packages for $APP_NAME $VERSION:"
ls -lh "$OUT" | sed 's/^/    /'
echo
echo "Output folder: $OUT"
