import shlex
import shutil
import subprocess

from .. import osinfo
from ..i18n import tr


def _applescript_quote(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _powershell_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def _launch_windows(script):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        return None
    subprocess.Popen([shell, "-NoExit", "-NoProfile", "-Command", script], creationflags=subprocess.CREATE_NEW_CONSOLE)
    return "powershell"


def _launch_mac(shell_command):
    pause = tr("Pulsa Enter para cerrar", "Press Enter to close")
    full = f"{shell_command}; echo; read -r -p {shlex.quote(pause)}"
    script = f'tell application "Terminal"\nactivate\ndo script "{_applescript_quote(full)}"\nend tell'
    subprocess.Popen(["osascript", "-e", script], start_new_session=True)
    return "Terminal"


def _launch_linux(shell_command):
    pause = tr("Enter para cerrar", "Press Enter to close")
    options = [
        ("konsole", ["--hold", "-e", "bash", "-c", shell_command]),
        ("gnome-terminal", ["--", "bash", "-c", shell_command + "; echo; read -p " + shlex.quote(pause)]),
        ("xfce4-terminal", ["--hold", "-e", f"bash -c {shlex.quote(shell_command)}"]),
        ("kitty", ["--hold", "bash", "-c", shell_command]),
        ("alacritty", ["--hold", "-e", "bash", "-c", shell_command]),
        ("xterm", ["-hold", "-e", "bash", "-c", shell_command]),
    ]
    for prog, args in options:
        if shutil.which(prog):
            subprocess.Popen([prog] + args, start_new_session=True)
            return prog
    return None


def launch_script(script):
    if osinfo.IS_WINDOWS:
        return _launch_windows(script)
    if osinfo.IS_MAC:
        return _launch_mac(script)
    return _launch_linux(script)


def launch_in_terminal(argv):
    if osinfo.IS_WINDOWS:
        return _launch_windows("& " + " ".join(_powershell_quote(a) for a in argv))
    return launch_script(" ".join(shlex.quote(a) for a in argv))
