import shutil

from .. import osinfo

LINUX_ADB = {
    "debian": ["sudo apt install -y adb fastboot"],
    "arch": ["sudo pacman -S --noconfirm android-tools"],
    "suse": ["sudo zypper install -y android-tools"],
    "fedora": ["sudo dnf install -y android-tools"],
}
LINUX_SCRCPY = {
    "debian": ["sudo apt install -y scrcpy"],
    "arch": ["sudo pacman -S --noconfirm scrcpy"],
    "suse": ["sudo zypper install -y scrcpy"],
    "fedora": ["sudo dnf install -y dnf-plugins-core", "sudo dnf copr enable -y zeno/scrcpy", "sudo dnf install -y scrcpy"],
}
ADB_COMMANDS = LINUX_ADB["fedora"]
SCRCPY_COMMANDS = LINUX_SCRCPY["fedora"]


def missing_tools():
    return [name for name in ("adb", "fastboot", "scrcpy") if not shutil.which(name)]


def install_script(missing=None):
    missing = list(missing) if missing is not None else ["adb", "scrcpy"]
    wants_adb = "adb" in missing or "fastboot" in missing
    wants_scrcpy = "scrcpy" in missing
    commands = []
    if osinfo.IS_WINDOWS:
        if wants_adb:
            commands.append("winget install --id Google.PlatformTools -e --accept-source-agreements --accept-package-agreements")
        if wants_scrcpy:
            commands.append("winget install --id Genymobile.scrcpy -e --accept-source-agreements --accept-package-agreements")
        return "; ".join(commands)
    if osinfo.IS_MAC:
        if wants_adb:
            commands.append("brew install --cask android-platform-tools")
        if wants_scrcpy:
            commands.append("brew install scrcpy")
        return " && ".join(commands)
    family = osinfo.linux_family() or "fedora"
    if wants_adb:
        commands += LINUX_ADB[family]
    if wants_scrcpy:
        commands += LINUX_SCRCPY[family]
    return " && ".join(commands)
