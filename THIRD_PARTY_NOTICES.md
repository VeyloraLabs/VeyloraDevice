# Third-party notices

VeyloraDevice is released under the **GNU GPL v3** (see [LICENSE](LICENSE)).
It is built on the following open source components. Each one keeps its own license.

## Python libraries (installed with `requirements.txt`)

| Component | License | Used for | Link |
|-----------|---------|----------|------|
| PySide6 (Qt for Python) | LGPL-3.0 / GPL-2.0 / GPL-3.0 | Windows, widgets and drawing | https://pypi.org/project/PySide6/ |
| PySide6-Fluent-Widgets | GPL-3.0 for non-commercial use, commercial license for commercial use | Fluent design components | https://github.com/zhiyiYo/PyQt-Fluent-Widgets |
| PySideSix-Frameless-Window | LGPL-3.0 | Frameless window (dependency of Fluent Widgets) | https://pypi.org/project/PySideSix-Frameless-Window/ |
| darkdetect | BSD-3-Clause | Dark/light theme detection (dependency of Fluent Widgets) | https://pypi.org/project/darkdetect/ |
| QtAwesome | MIT | Icons (Font Awesome set) | https://pypi.org/project/QtAwesome/ |
| requests | Apache-2.0 | Downloads (firmware lists, update check, device photos) | https://pypi.org/project/requests/ |

Font Awesome Free, bundled inside QtAwesome: icons CC BY 4.0, fonts SIL OFL 1.1, code MIT.

## Build tools (only used to compile, not shipped)

| Component | License |
|-----------|---------|
| PyInstaller | GPL-2.0 with the bootloader exception (programs it builds can use any license) |
| dpkg-deb, rpmbuild, appimagetool | Their own licenses |

## Programs VeyloraDevice calls (not included, installed separately)

VeyloraDevice runs these as separate programs and does not bundle them:
`libimobiledevice` tools (`ideviceinfo`, `idevicebackup2`, `idevicerestore`, ...), `usbmuxd`,
`adb` and `fastboot` (Android platform tools) and, optionally, `scrcpy`.
Each one has its own license; check the package of your distribution.

## Online services

- **ipsw.me** (public API) for the list of Apple firmware files.
- **Wikipedia / Wikimedia** (public API) for illustrative device photos; images stay under their own free licenses and are not redistributed here.
- **Google Play supported devices list** to translate model codes into commercial names.
- **GitHub API** to detect new VeyloraDevice releases.

## Important to know before using it commercially

PySide6-Fluent-Widgets is dual licensed. Using it for commercial purposes requires
buying its commercial license: https://qfluentwidgets.com/price

## Trademarks

Apple, iPhone, iPad and iOS are trademarks of Apple Inc. Android is a trademark of Google LLC.
VeyloraDevice is an independent project and is not affiliated with those companies.
