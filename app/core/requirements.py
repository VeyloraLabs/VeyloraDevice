import shutil

ADB_COMMANDS = ["sudo dnf install -y android-tools"]
SCRCPY_COMMANDS = ["sudo dnf install -y dnf-plugins-core", "sudo dnf copr enable -y zeno/scrcpy",
                   "sudo dnf install -y scrcpy"]


def missing_tools():
    return [name for name in ("adb", "fastboot", "scrcpy") if not shutil.which(name)]


def install_script(missing=None):
    missing = list(missing) if missing is not None else ["adb", "scrcpy"]
    commands = []
    if "adb" in missing or "fastboot" in missing:
        commands += ADB_COMMANDS
    if "scrcpy" in missing:
        commands += SCRCPY_COMMANDS
    return " && ".join(commands)
