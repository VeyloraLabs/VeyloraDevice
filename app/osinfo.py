import os
import platform
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def system_label():
    if IS_WINDOWS:
        return "Windows"
    if IS_MAC:
        return "macOS"
    return "Linux"


def machine():
    value = platform.machine().lower()
    if value in ("amd64", "x86_64", "x64"):
        return "x86_64"
    if value in ("arm64", "aarch64"):
        return "arm64"
    return value


def linux_family():
    if not IS_LINUX:
        return ""
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            text = handle.read().lower()
    except OSError:
        return ""
    if any(word in text for word in ("debian", "ubuntu", "mint", "pop", "elementary", "kali")):
        return "debian"
    if any(word in text for word in ("fedora", "rhel", "centos", "rocky", "alma", "mageia")):
        return "fedora"
    if "suse" in text:
        return "suse"
    if any(word in text for word in ("arch", "manjaro", "endeavour", "garuda")):
        return "arch"
    return ""


def resource_roots():
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
        executable = Path(sys.executable).resolve()
        if IS_MAC:
            roots += [executable.parent.parent / "Resources", executable.parent.parent / "Frameworks"]
        roots.append(executable.parent)
    else:
        roots.append(Path(__file__).resolve().parents[1])
    return roots


def bundled_tool_dirs():
    found = []
    for root in resource_roots():
        for name in ("platform-tools", "bin"):
            candidate = root / "tools" / name
            if candidate.is_dir() and candidate not in found:
                found.append(candidate)
    return found


def extra_search_dirs():
    if IS_MAC:
        return [Path(p) for p in ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/local/sbin",
                                  "/opt/local/bin")]
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        candidates = []
        if local:
            candidates.append(Path(local) / "Microsoft" / "WinGet" / "Links")
        if program_files:
            candidates.append(Path(program_files) / "libimobiledevice")
        return candidates
    return []


def extend_path():
    current = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    first = [str(p) for p in bundled_tool_dirs()]
    last = [str(p) for p in extra_search_dirs() if p.is_dir()]
    ordered = []
    for entry in first + current + last:
        if entry not in ordered:
            ordered.append(entry)
    os.environ["PATH"] = os.pathsep.join(ordered)


def cache_dir():
    home = Path.home()
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "VeyloraDevice" / "Cache"
    if IS_MAC:
        return home / "Library" / "Caches" / "VeyloraDevice"
    return home / ".cache" / "veylora"


def hidden_console_kwargs():
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def detached_kwargs():
    if IS_WINDOWS:
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def hide_console(process):
    if IS_WINDOWS and hasattr(process, "setCreateProcessArgumentsModifier"):
        def modifier(args):
            args.flags |= 0x08000000

        process.setCreateProcessArgumentsModifier(modifier)


def set_windows_app_id(app_id):
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass
