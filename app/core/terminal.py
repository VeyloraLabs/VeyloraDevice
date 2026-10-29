import shlex
import shutil
import subprocess

from ..i18n import tr


def launch_in_terminal(argv):
    cmd = " ".join(shlex.quote(a) for a in argv)
    options = [
        ("konsole", ["--hold", "-e", "bash", "-c", cmd]),
        ("gnome-terminal", ["--", "bash", "-c", cmd + "; echo; read -p " + shlex.quote(tr("Enter para cerrar", "Press Enter to close"))]),
        ("xfce4-terminal", ["--hold", "-e", f"bash -c {shlex.quote(cmd)}"]),
        ("kitty", ["--hold", "bash", "-c", cmd]),
        ("alacritty", ["--hold", "-e", "bash", "-c", cmd]),
        ("xterm", ["-hold", "-e", "bash", "-c", cmd]),
    ]
    for prog, args in options:
        if shutil.which(prog):
            subprocess.Popen([prog] + args, start_new_session=True)
            return prog
    return None
