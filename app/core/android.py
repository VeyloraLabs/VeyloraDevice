import posixpath
import re
import shlex
import time
from pathlib import Path

from .tools import ToolMissing, run
from ..i18n import tr


class AndroidError(Exception):
    pass


def _text(out, err):
    return (out + err).decode(errors="replace").strip()


def _run_adb(args, timeout=20, include_stderr=False):
    rc, out, err = run(["adb", *args], timeout=timeout)
    if rc != 0:
        raise AndroidError(_text(out, err) or tr(f"adb terminó con código {rc}", f"adb exited with code {rc}"))
    output = _text(out, err) if include_stderr else out.decode(errors="replace").strip()
    return output


def parse_devices(output):
    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached") or line.startswith("*"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        serial, status = parts[:2]
        if status == "no" and len(parts) == 3 and parts[2].startswith("permissions"):
            status = "no permissions"
        details = {}
        if len(parts) == 3:
            for item in parts[2].split():
                if ":" in item:
                    key, value = item.split(":", 1)
                    details[key] = value
        devices.append({
            "serial": serial,
            "status": status,
            "model": details.get("model", ""),
            "product": details.get("product", ""),
            "device": details.get("device", ""),
        })
    return devices


def list_devices():
    return parse_devices(_run_adb(["devices", "-l"], timeout=20))


def parse_properties(output):
    properties = {}
    for line in output.splitlines():
        match = re.fullmatch(r"\[([^\]]+)\]: \[(.*)\]", line.strip())
        if match:
            properties[match.group(1)] = match.group(2)
    return properties


def get_properties(serial):
    output = _run_adb(["-s", serial, "shell", "getprop"], timeout=30)
    properties = parse_properties(output)
    if not properties:
        raise AndroidError(tr("ADB no devolvió propiedades del dispositivo.",
                              "ADB returned no device properties."))
    return properties


REBOOT_MODES = {
    "system": [],
    "recovery": ["recovery"],
    "bootloader": ["bootloader"],
    "fastboot": ["fastboot"],
    "sideload": ["sideload"],
}


def reboot(serial, mode="system"):
    if mode == "poweroff":
        _run_adb(["-s", serial, "shell", "reboot", "-p"], timeout=30)
        return
    if mode not in REBOOT_MODES:
        raise AndroidError(tr(f"Modo de reinicio desconocido: {mode}", f"Unknown reboot mode: {mode}"))
    _run_adb(["-s", serial, "reboot", *REBOOT_MODES[mode]], timeout=30)


def install_apk(serial, path):
    output = _run_adb(["-s", serial, "install", "-r", path], timeout=180, include_stderr=True)
    if "success" not in output.lower():
        raise AndroidError(output.strip() or tr("ADB no confirmó la instalación del APK.",
                                                "ADB did not confirm APK installation."))
    return output.strip()


def poll():
    try:
        devices = list_devices()
        error = ""
    except ToolMissing as exc:
        return {"available": False, "devices": [], "error": str(exc)}
    except AndroidError as exc:
        devices, error = [], str(exc)
    try:
        known = {d["serial"] for d in devices}
        devices += [d for d in fastboot_devices() if d["serial"] not in known]
    except (ToolMissing, AndroidError):
        pass
    return {"available": True, "devices": devices, "error": error}


_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
_HOSTPORT_RE = re.compile(r"^[A-Za-z0-9.\-]+:\d{1,5}$")
PROTECTED_PATHS = {"/", "/sdcard", "/storage", "/storage/emulated", "/storage/emulated/0", "/storage/self",
                   "/storage/self/primary", "/data", "/system", "/vendor", "/product", "/cache", "/mnt"}


def _check_package(package):
    if not _PACKAGE_RE.match(package or ""):
        raise AndroidError(tr(f"Nombre de paquete no válido: {package!r}", f"Invalid package name: {package!r}"))
    return package


def _check_hostport(value):
    value = (value or "").strip()
    if not _HOSTPORT_RE.match(value):
        raise AndroidError(tr("Escribe la dirección como IP:puerto (por ejemplo 192.168.1.20:5555).",
                              "Write the address as IP:port (for example 192.168.1.20:5555)."))
    return value


def clean_path(path):
    path = (path or "").strip() or "/sdcard"
    return posixpath.normpath("/" + path.lstrip("/"))


def _shell(serial, command, timeout=30, include_stderr=False):
    return _run_adb(["-s", serial, "shell", command], timeout=timeout, include_stderr=include_stderr)


def device_label(device):
    name = device.get("model") or device.get("product") or device.get("serial") or ""
    return name.replace("_", " ")


_OVERVIEW_SCRIPT = (
    "echo '##BATTERY'; dumpsys battery; "
    "echo '##DF'; df -k /data; "
    "echo '##MEM'; head -n 3 /proc/meminfo; "
    "echo '##UP'; cat /proc/uptime; "
    "echo '##WM'; wm size; wm density; "
    "echo '##IP'; ip -f inet addr show wlan0; "
    "echo '##THERMAL'; for z in /sys/class/thermal/thermal_zone*; do echo \"$(cat $z/type) $(cat $z/temp)\"; done 2>/dev/null"
)
BATTERY_STATUS = {1: ("Desconocido", "Unknown"), 2: ("Cargando", "Charging"), 3: ("Descargando", "Discharging"),
                  4: ("Sin cargar", "Not charging"), 5: ("Completa", "Full")}
BATTERY_HEALTH = {1: ("Desconocida", "Unknown"), 2: ("Buena", "Good"), 3: ("Sobrecalentada", "Overheated"),
                  4: ("Dañada", "Dead"), 5: ("Sobrevoltaje", "Over voltage"), 6: ("Fallo", "Failure"),
                  7: ("Fría", "Cold")}


def _sections(output):
    sections, current = {}, None
    for line in output.splitlines():
        if line.startswith("##"):
            current = line[2:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {key: "\n".join(lines) for key, lines in sections.items()}


def _int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_battery(text):
    values = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    level, scale = _int(values.get("level")), _int(values.get("scale"), 100) or 100
    temperature = _int(values.get("temperature"))
    plugged = any(values.get(k) == "true" for k in ("ac powered", "usb powered", "wireless powered"))
    return {
        "level": None if level is None else round(level * 100 / scale),
        "status": _int(values.get("status")),
        "health": _int(values.get("health")),
        "temperature": None if temperature is None else temperature / 10,
        "voltage": _int(values.get("voltage")),
        "technology": values.get("technology", ""),
        "plugged": plugged,
    }


def parse_df(text):
    lines = [line for line in text.splitlines() if line.strip() and not line.lower().startswith("filesystem")]
    tokens = " ".join(lines).split()
    if len(tokens) < 5:
        return None
    total, used = _int(tokens[-5]), _int(tokens[-4])
    if total is None or used is None:
        return None
    return total * 1024, used * 1024


def parse_meminfo(text):
    values = {}
    for line in text.splitlines():
        match = re.match(r"(\w+):\s+(\d+)\s*kB", line.strip())
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    total = values.get("MemTotal")
    if not total:
        return None
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return total, max(0, total - available)


def parse_cpu_temperature(text):
    best = None
    for line in text.splitlines():
        parts = line.rsplit(None, 1)
        if len(parts) != 2 or not re.search(r"cpu|soc|tsens|cluster|big|little|mtk", parts[0].lower()):
            continue
        try:
            value = float(parts[1])
        except ValueError:
            continue
        if abs(value) > 1000:
            value /= 1000
        if 10 <= value <= 120 and (best is None or value > best):
            best = value
    return best


def parse_overview(output):
    parts = _sections(output)
    wm = parts.get("WM", "")
    sizes = re.findall(r"(?:Override|Physical) size:\s*(\d+x\d+)", wm)
    density = re.findall(r"(?:Override|Physical) density:\s*(\d+)", wm)
    uptime = re.match(r"\s*([\d.]+)", parts.get("UP", ""))
    ip = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", parts.get("IP", ""))
    return {
        "battery": parse_battery(parts.get("BATTERY", "")),
        "storage": parse_df(parts.get("DF", "")),
        "memory": parse_meminfo(parts.get("MEM", "")),
        "uptime": float(uptime.group(1)) if uptime else None,
        "screen": sizes[-1] if sizes else "",
        "density": int(density[-1]) if density else None,
        "ip": ip.group(1) if ip else "",
        "cpu_temp": parse_cpu_temperature(parts.get("THERMAL", "")),
    }


def get_overview(serial):
    return parse_overview(_shell(serial, _OVERVIEW_SCRIPT, timeout=30))


def screenshot(serial):
    rc, out, err = run(["adb", "-s", serial, "exec-out", "screencap", "-p"], timeout=30)
    if rc != 0 or not out.startswith(b"\x89PNG"):
        raise AndroidError(_text(b"", err) or tr("No se pudo capturar la pantalla (¿está bloqueada o protegida?).",
                                                 "Could not capture the screen (is it locked or protected?)."))
    return out


def record_screen(serial, local_path, seconds=30):
    seconds = max(1, min(int(seconds), 180))
    remote = f"/sdcard/veyloradevice_{int(time.time())}.mp4"
    try:
        _run_adb(["-s", serial, "shell", "screenrecord", "--time-limit", str(seconds), remote],
                 timeout=seconds + 40, include_stderr=True)
        _run_adb(["-s", serial, "pull", remote, str(local_path)], timeout=300, include_stderr=True)
    finally:
        try:
            _run_adb(["-s", serial, "shell", "rm", "-f", remote], timeout=15)
        except (AndroidError, ToolMissing):
            pass
    return str(local_path)


KEYS = {"back": 4, "home": 3, "recents": 187, "power": 26, "volume_up": 24, "volume_down": 25, "mute": 164,
        "wake": 224, "sleep": 223, "menu": 82, "enter": 66, "play_pause": 85, "next": 87, "previous": 88}
ALT_KEYS = {
    "home": "am start -a android.intent.action.MAIN -c android.intent.category.HOME",
    "volume_up": "cmd media_session volume --show --stream 3 --adj raise",
    "volume_down": "cmd media_session volume --show --stream 3 --adj lower",
    "mute": "cmd media_session volume --show --stream 3 --adj toggle-mute",
    "play_pause": "cmd media_session dispatch play-pause",
    "next": "cmd media_session dispatch next",
    "previous": "cmd media_session dispatch previous",
}
SYSTEM_ACTIONS = {
    "notifications": "cmd statusbar expand-notifications",
    "quick_settings": "cmd statusbar expand-settings",
    "collapse": "cmd statusbar collapse",
}
INPUT_RETRY_AFTER = 30
_input_blocked = {}


class InputBlockedError(AndroidError):
    pass


BLOCKED_HELP = ("El móvil no deja controlar los toques desde el PC. Es un bloqueo de seguridad de Xiaomi/Redmi/POCO "
                "(y de algunas otras marcas): en Opciones de desarrollador activa «Depuración USB (ajustes de "
                "seguridad)» y vuelve a probar.",
                "The phone does not allow input from the computer. It is a security lock on Xiaomi/Redmi/POCO (and "
                "some other brands): in Developer options turn on “USB debugging (Security settings)” and try again.")


def short_text(text, lines=3, chars=320):
    useful = [line.strip() for line in str(text).splitlines() if line.strip() and not line.strip().startswith("at ")]
    out = " ".join(useful[:lines]) or str(text).strip()
    return out if len(out) <= chars else out[:chars - 1] + "…"


def _is_blocked(text):
    lowered = text.lower()
    return "inject_events" in lowered or "securityexception" in lowered or "injecting input" in lowered


def _shell_result(serial, command, timeout):
    try:
        return _shell(serial, command, timeout=timeout, include_stderr=True).strip(), None
    except AndroidError as exc:
        return str(exc).strip(), exc


def _input(serial, command):
    output, error = _shell_result(serial, command, 15)
    if _is_blocked(output):
        _input_blocked[serial] = time.time()
        raise InputBlockedError(tr(*BLOCKED_HELP))
    if error:
        raise AndroidError(short_text(output))
    lowered = output.lower()
    if output and ("exception" in lowered or "error" in lowered or "denied" in lowered or "not found" in lowered):
        raise AndroidError(short_text(output))


def _system_command(serial, command):
    output, error = _shell_result(serial, command, 20)
    lowered = output.lower()
    if _is_blocked(output):
        raise InputBlockedError(tr(*BLOCKED_HELP))
    if "no shell command implementation" in lowered or "unknown command" in lowered or (
            error and "exception" in lowered):
        raise AndroidError(tr("Este Android no admite esa acción desde el PC.",
                              "This Android does not support that action from the computer."))
    if error:
        raise AndroidError(short_text(output))


def input_blocked(serial):
    return time.time() - _input_blocked.get(serial, 0) < INPUT_RETRY_AFTER


def send_key(serial, key):
    if key in SYSTEM_ACTIONS:
        _system_command(serial, SYSTEM_ACTIONS[key])
        return
    if key not in KEYS:
        raise AndroidError(tr(f"Tecla desconocida: {key}", f"Unknown key: {key}"))
    if not input_blocked(serial):
        try:
            _input(serial, f"input keyevent {KEYS[key]}")
            return
        except InputBlockedError:
            if key not in ALT_KEYS:
                raise
    if key in ALT_KEYS:
        _system_command(serial, ALT_KEYS[key])
        return
    raise InputBlockedError(tr(*BLOCKED_HELP))


def send_text(serial, text):
    if not text:
        return
    if not text.isascii():
        raise AndroidError(tr("Android solo permite escribir caracteres ASCII (sin tildes ni emojis) por ADB.",
                              "Android only accepts ASCII characters (no accents or emoji) over ADB."))
    escaped = text.replace(" ", "%s")
    _input(serial, "input text " + shlex.quote(escaped))


def input_allowed(serial):
    try:
        _input(serial, "input keyevent 0")
        _input_blocked.pop(serial, None)
        return True
    except InputBlockedError:
        return False


def open_developer_options(serial):
    _shell(serial, "am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS", timeout=15)


def open_url(serial, url):
    url = (url or "").strip()
    if not re.match(r"^https?://\S+$", url):
        raise AndroidError(tr("Escribe un enlace que empiece por http:// o https://",
                              "Enter a link that starts with http:// or https://"))
    _shell(serial, "am start -a android.intent.action.VIEW -d " + shlex.quote(url), timeout=20)


def restart_server():
    _run_adb(["kill-server"], timeout=15)
    _run_adb(["start-server"], timeout=30, include_stderr=True)


def device_ip(serial):
    output = _shell(serial, "ip -f inet addr show wlan0", timeout=15)
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", output)
    if not match:
        raise AndroidError(tr("El móvil no tiene IP de Wi-Fi. Conéctalo a la misma red que el PC.",
                              "The phone has no Wi-Fi IP. Connect it to the same network as this computer."))
    return match.group(1)


def enable_tcpip(serial, port=5555):
    _run_adb(["-s", serial, "tcpip", str(int(port))], timeout=20, include_stderr=True)
    return f"{device_ip(serial)}:{int(port)}"


def pair_wifi(address, code):
    address = _check_hostport(address)
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise AndroidError(tr("El código de emparejamiento tiene 6 dígitos.", "The pairing code has 6 digits."))
    output = _run_adb(["pair", address, code], timeout=30, include_stderr=True)
    if "successfully paired" not in output.lower():
        raise AndroidError(output or tr("No se pudo emparejar.", "Pairing failed."))
    return output


def connect_wifi(address):
    address = _check_hostport(address)
    output = _run_adb(["connect", address], timeout=25, include_stderr=True)
    if not re.search(r"\b(connected to|already connected to)\b", output.lower()):
        raise AndroidError(output or tr("No se pudo conectar.", "Could not connect."))
    return output


def disconnect_wifi(address=None):
    args = ["disconnect"] + ([_check_hostport(address)] if address else [])
    _run_adb(args, timeout=15, include_stderr=True)


_PKG_SCRIPT = ("echo '##USER'; pm list packages -f -3; echo '##SYSTEM'; pm list packages -f -s; "
               "echo '##DISABLED'; pm list packages -d; echo '##ALL'; pm list packages -u")


def parse_package_lines(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        body = line[len("package:"):]
        if "=" in body:
            path, package = body.rsplit("=", 1)
        else:
            path, package = "", body
        if package:
            result[package] = path
    return result


def parse_packages(output):
    parts = _sections(output)
    user = parse_package_lines(parts.get("USER", ""))
    system = parse_package_lines(parts.get("SYSTEM", ""))
    disabled = set(parse_package_lines(parts.get("DISABLED", "")))
    everything = set(parse_package_lines(parts.get("ALL", "")))
    apps = []
    for package, path in {**system, **user}.items():
        apps.append({"package": package, "path": path, "system": package not in user,
                     "disabled": package in disabled, "removed": False})
    for package in everything - set(user) - set(system):
        apps.append({"package": package, "path": "", "system": True, "disabled": False, "removed": True})
    apps.sort(key=lambda a: a["package"].lower())
    return apps


def list_packages(serial):
    return parse_packages(_shell(serial, _PKG_SCRIPT, timeout=60))


def parse_package_details(output):
    def grab(pattern):
        match = re.search(pattern, output)
        return match.group(1).strip() if match else ""

    return {
        "version_name": grab(r"versionName=(\S+)"),
        "version_code": grab(r"versionCode=(\d+)"),
        "first_install": grab(r"firstInstallTime=(.+)"),
        "last_update": grab(r"lastUpdateTime=(.+)"),
        "target_sdk": grab(r"targetSdk=(\d+)"),
        "min_sdk": grab(r"minSdk=(\d+)"),
        "installer": grab(r"installerPackageName=(\S+)"),
        "uid": grab(r"userId=(\d+)"),
        "data_dir": grab(r"dataDir=(\S+)"),
    }


def package_details(serial, package):
    _check_package(package)
    return parse_package_details(_shell(serial, f"dumpsys package {package}", timeout=30))


def launch_app(serial, package):
    _check_package(package)
    output = _shell(serial, f"monkey -p {package} -c android.intent.category.LAUNCHER 1", timeout=20,
                    include_stderr=True)
    if "no activities found" in output.lower() or "monkey aborted" in output.lower():
        raise AndroidError(tr("Esta app no tiene pantalla que abrir.", "This app has no screen to open."))


def force_stop(serial, package):
    _check_package(package)
    _shell(serial, f"am force-stop {package}", timeout=15)


def open_app_settings(serial, package):
    _check_package(package)
    _shell(serial, f"am start -a android.settings.APPLICATION_DETAILS_SETTINGS -d package:{package}", timeout=15)


def _expect_success(output, what):
    if "success" not in output.lower():
        raise AndroidError(output.strip() or what)
    return output.strip()


def clear_data(serial, package):
    _check_package(package)
    return _expect_success(_shell(serial, f"pm clear {package}", timeout=30, include_stderr=True),
                           tr("No se pudieron borrar los datos.", "Could not clear the data."))


def uninstall(serial, package, system=False):
    _check_package(package)
    flag = "--user 0 " if system else ""
    return _expect_success(_shell(serial, f"pm uninstall {flag}{package}", timeout=60, include_stderr=True),
                           tr("No se pudo desinstalar.", "Could not uninstall."))


def set_enabled(serial, package, enabled):
    _check_package(package)
    command = f"pm enable {package}" if enabled else f"pm disable-user --user 0 {package}"
    output = _shell(serial, command, timeout=20, include_stderr=True)
    if "new state" not in output.lower():
        raise AndroidError(output.strip() or tr("No se pudo cambiar el estado de la app.",
                                                "Could not change the app state."))


def restore_system_app(serial, package):
    _check_package(package)
    output = _shell(serial, f"cmd package install-existing {package}", timeout=30, include_stderr=True)
    if "installed for user" not in output.lower():
        raise AndroidError(output.strip() or tr("No se pudo restaurar la app.", "Could not restore the app."))


def extract_apk(serial, package, dest_dir):
    _check_package(package)
    paths = [line[len("package:"):].strip()
             for line in _shell(serial, f"pm path {package}", timeout=20).splitlines()
             if line.startswith("package:")]
    if not paths:
        raise AndroidError(tr("No se encontró el APK de esta app.", "Could not find this app's APK."))
    dest = Path(dest_dir)
    created = []
    if len(paths) == 1:
        target = dest / f"{package}.apk"
        _run_adb(["-s", serial, "pull", paths[0], str(target)], timeout=300, include_stderr=True)
        created.append(str(target))
    else:
        folder = dest / package
        folder.mkdir(parents=True, exist_ok=True)
        for remote in paths:
            _run_adb(["-s", serial, "pull", remote, str(folder)], timeout=300, include_stderr=True)
            created.append(str(folder / posixpath.basename(remote)))
    return created


INSTALL_ERRORS = {
    "INSTALL_FAILED_VERSION_DOWNGRADE": ("Ya hay una versión más nueva instalada.",
                                         "A newer version is already installed."),
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": ("La firma no coincide con la app instalada.",
                                           "The signature does not match the installed app."),
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": ("No hay espacio suficiente en el móvil.",
                                            "Not enough storage on the phone."),
    "INSTALL_FAILED_OLDER_SDK": ("Tu versión de Android es demasiado antigua para esta app.",
                                 "Your Android version is too old for this app."),
    "INSTALL_FAILED_NO_MATCHING_ABIS": ("La app no es compatible con el procesador de este móvil.",
                                        "The app does not support this phone's processor."),
    "INSTALL_FAILED_USER_RESTRICTED": ("El móvil bloquea instalar por USB. En Opciones de desarrollador activa "
                                       "«Instalar vía USB».",
                                       "The phone blocks USB installs. Enable “Install via USB” in Developer options."),
    "INSTALL_FAILED_ABORTED": ("El móvil canceló la instalación. Acepta el aviso en la pantalla si sale.",
                               "The phone cancelled the install. Accept the prompt on screen if it appears."),
    "INSTALL_FAILED_ALREADY_EXISTS": ("La app ya está instalada.", "The app is already installed."),
    "INSTALL_PARSE_FAILED_NOT_APK": ("El archivo no es un APK válido.", "The file is not a valid APK."),
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": ("El APK no está firmado.", "The APK is not signed."),
    "INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION": ("El APK está dañado.", "The APK is corrupted."),
    "INSTALL_FAILED_INVALID_APK": ("El APK está dañado o incompleto.", "The APK is damaged or incomplete."),
    "INSTALL_FAILED_TEST_ONLY": ("Es un APK de pruebas y el móvil no lo acepta.",
                                 "This is a test-only APK and the phone rejects it."),
}


class InstallError(AndroidError):
    def __init__(self, code, message, package="", raw=""):
        super().__init__(message)
        self.code = code
        self.package = package
        self.raw = raw


def explain_install_error(output):
    match = re.search(r"(INSTALL_[A-Z_]+)", output)
    code = match.group(1) if match else ""
    package = ""
    pkg_match = re.search(r"Package (\S+) signatures do not match", output) or re.search(r"Package (\S+) ", output)
    if pkg_match and _PACKAGE_RE.match(pkg_match.group(1)):
        package = pkg_match.group(1)
    if code in INSTALL_ERRORS:
        es, en = INSTALL_ERRORS[code]
        return InstallError(code, tr(es, en), package, output.strip())
    return InstallError(code, output.strip() or tr("ADB no confirmó la instalación del APK.",
                                                   "ADB did not confirm APK installation."),
                        package, output.strip())


def install_apks(serial, paths, downgrade=False, grant=False, split=False):
    paths = [str(p) for p in paths]
    if not paths:
        raise AndroidError(tr("No hay ningún APK que instalar.", "There is no APK to install."))
    flags = ["-r"] + (["-d"] if downgrade else []) + (["-g"] if grant else [])
    command = "install-multiple" if split and len(paths) > 1 else "install"
    if command == "install" and len(paths) > 1:
        raise AndroidError("install_apks: use one call per file")
    rc, out, err = run(["adb", "-s", serial, command, *flags, *paths], timeout=300)
    text = _text(out, err)
    if rc != 0 or "success" not in text.lower():
        raise explain_install_error(text)
    return text


_LS_MODERN = re.compile(
    r"^([-dlcbps][rwxsStTl-]{9}\.?)\s+\d+\s+(\S+)\s+(\S+)\s+(?:(\d+)|\d+,\s*\d+)\s+"
    r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(.+)$")
_LS_OLD = re.compile(
    r"^([-dlcbps][rwxsStTl-]{9}\.?)\s+(\S+)\s+(\S+)\s+(?:(\d+)\s+)?"
    r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(.+)$")


def parse_ls(output):
    entries = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line or line.startswith("total "):
            continue
        match = _LS_MODERN.match(line) or _LS_OLD.match(line)
        if not match:
            continue
        perms, owner, group, size, date, clock, name = match.groups()
        link_target = ""
        if perms[0] == "l" and " -> " in name:
            name, link_target = name.split(" -> ", 1)
        if name in (".", ".."):
            continue
        entries.append({
            "name": name,
            "is_dir": perms[0] == "d",
            "is_link": perms[0] == "l",
            "size": int(size) if size else 0,
            "modified": f"{date} {clock}",
            "perms": perms.rstrip("."),
            "owner": owner,
            "target": link_target,
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


def list_dir(serial, path):
    path = clean_path(path)
    rc, out, err = run(["adb", "-s", serial, "shell", f"ls -lAL {shlex.quote(path.rstrip('/') + '/')}"], timeout=30)
    text = out.decode(errors="replace")
    entries = parse_ls(text)
    if rc != 0 and not entries:
        message = _text(b"", err) or text.strip()
        if "permission denied" in message.lower():
            raise AndroidError(tr("Android no deja ver esta carpeta (sin permiso).",
                                  "Android does not allow viewing this folder (permission denied)."))
        if "no such file" in message.lower():
            raise AndroidError(tr("Esa carpeta no existe.", "That folder does not exist."))
        raise AndroidError(message or tr("No se pudo leer la carpeta.", "Could not read the folder."))
    return entries


def pull_path(serial, remote, local_dir):
    _run_adb(["-s", serial, "pull", clean_path(remote), str(local_dir)], timeout=3600, include_stderr=True)


def push_path(serial, local, remote_dir):
    _run_adb(["-s", serial, "push", str(local), clean_path(remote_dir) + "/"], timeout=3600, include_stderr=True)


def make_dir(serial, path):
    _shell(serial, f"mkdir -p {shlex.quote(clean_path(path))}", timeout=15, include_stderr=True)


def _check_not_protected(path):
    path = clean_path(path)
    if path in PROTECTED_PATHS:
        raise AndroidError(tr(f"Por seguridad no se puede modificar {path}.",
                              f"For safety {path} cannot be modified."))
    return path


def delete_path(serial, path):
    path = _check_not_protected(path)
    _shell(serial, f"rm -rf {shlex.quote(path)}", timeout=120, include_stderr=True)


def rename_path(serial, old, new_name):
    old = _check_not_protected(old)
    if not new_name or "/" in new_name or new_name in (".", ".."):
        raise AndroidError(tr("El nombre no puede estar vacío ni contener «/».",
                              "The name cannot be empty or contain “/”."))
    new = posixpath.join(posixpath.dirname(old), new_name)
    _shell(serial, f"mv {shlex.quote(old)} {shlex.quote(new)}", timeout=30, include_stderr=True)
    return new


_LOG_LEVEL = re.compile(r"^\S+\s+\S+\s+\d+\s+\d+\s+([VDIWEFA])\s")
LOG_LEVELS = "VDIWEF"


def parse_logcat_level(line):
    match = _LOG_LEVEL.match(line)
    return match.group(1) if match else ""


def level_allowed(level, minimum):
    if not level:
        return True
    order = LOG_LEVELS + "A"
    return order.index(level) >= order.index(minimum)


def _run_fastboot(args, timeout=15):
    rc, out, err = run(["fastboot", *args], timeout=timeout)
    return rc, _text(out, err)


def parse_fastboot_devices(output):
    devices = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower() in ("fastboot", "fastbootd"):
            devices.append({"serial": parts[0], "status": "fastboot", "model": "", "product": "", "device": ""})
    return devices


def fastboot_devices():
    rc, text = _run_fastboot(["devices"])
    if rc != 0:
        return []
    return parse_fastboot_devices(text)


FASTBOOT_VARS = (("product", "Producto", "Product"), ("version-bootloader", "Versión del bootloader", "Bootloader version"),
                 ("unlocked", "Bootloader desbloqueado", "Bootloader unlocked"),
                 ("secure", "Arranque seguro", "Secure boot"), ("current-slot", "Ranura activa", "Active slot"),
                 ("is-userspace", "Fastbootd (espacio de usuario)", "Fastbootd (userspace)"),
                 ("battery-voltage", "Voltaje de batería", "Battery voltage"), ("serialno", "Número de serie", "Serial"))


def fastboot_info(serial):
    rows = []
    for var, es, en in FASTBOOT_VARS:
        rc, text = _run_fastboot(["-s", serial, "getvar", var])
        match = re.search(rf"^{re.escape(var)}:\s*(.+)$", text, re.MULTILINE)
        if match and match.group(1).strip():
            rows.append((tr(es, en), match.group(1).strip()))
    if not rows:
        raise AndroidError(tr("No se pudo leer la información en modo Fastboot.", "Could not read Fastboot information."))
    return rows


def fastboot_reboot(serial, mode="system"):
    args = {"system": ["reboot"], "bootloader": ["reboot", "bootloader"]}.get(mode)
    if args is None:
        raise AndroidError(tr(f"Modo de reinicio desconocido: {mode}", f"Unknown reboot mode: {mode}"))
    rc, text = _run_fastboot(["-s", serial, *args], timeout=30)
    if rc != 0:
        raise AndroidError(text or tr("No se pudo reiniciar.", "Could not reboot."))
