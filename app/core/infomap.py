import json
from dataclasses import dataclass

from ..i18n import tr
from .util import fmt_bytes

CATEGORIES = {
    "id": ("Identificación", "Identification"),
    "software": ("Software", "Software"),
    "hardware": ("Hardware", "Hardware"),
    "network": ("Red y conectividad", "Network & connectivity"),
    "battery": ("Batería y almacenamiento", "Battery & storage"),
    "security": ("Activación y seguridad", "Activation & security"),
    "recovery": ("Recovery / DFU", "Recovery / DFU"),
    "other": ("Otros", "Other"),
}
CATEGORY_ORDER = list(CATEGORIES)


def category_label(cat):
    es, en = CATEGORIES.get(cat, (cat, cat))
    return tr(es, en)


KEYMAP = {
    "DeviceName": ("id", "Nombre del dispositivo", "Device name"),
    "ProductType": ("id", "Identificador de modelo", "Model identifier"),
    "ModelNumber": ("id", "Número de modelo", "Model number"),
    "RegionInfo": ("id", "Región del modelo", "Model region"),
    "HardwareModel": ("id", "Modelo de placa", "Board model"),
    "SerialNumber": ("id", "Número de serie", "Serial number"),
    "UniqueDeviceID": ("id", "UDID", "UDID"),
    "UniqueChipID": ("id", "ECID", "ECID"),
    "InternationalMobileEquipmentIdentity": ("id", "IMEI", "IMEI"),
    "InternationalMobileEquipmentIdentity2": ("id", "IMEI 2", "IMEI 2"),
    "MobileEquipmentIdentifier": ("id", "MEID", "MEID"),
    "PhoneNumber": ("id", "Número de teléfono", "Phone number"),
    "DeviceColor": ("id", "Color", "Color"),
    "DeviceEnclosureColor": ("id", "Color de la carcasa", "Enclosure color"),
    "DeviceClass": ("id", "Clase de dispositivo", "Device class"),
    "ProductName": ("software", "Sistema", "System"),
    "ProductVersion": ("software", "Versión del sistema", "System version"),
    "BuildVersion": ("software", "Build", "Build"),
    "FirmwareVersion": ("software", "Firmware (iBoot)", "Firmware (iBoot)"),
    "BasebandVersion": ("software", "Versión del módem (baseband)", "Modem version (baseband)"),
    "BasebandStatus": ("software", "Estado del módem", "Modem status"),
    "TimeZone": ("software", "Zona horaria", "Time zone"),
    "Locale": ("software", "Región/idioma", "Region/language"),
    "UseRaptorCerts": ("software", "Certificados Raptor", "Raptor certificates"),
    "CPUArchitecture": ("hardware", "Arquitectura de CPU", "CPU architecture"),
    "ChipID": ("hardware", "ID del chip", "Chip ID"),
    "BoardId": ("hardware", "ID de placa", "Board ID"),
    "HardwarePlatform": ("hardware", "Plataforma (chip)", "Platform (chip)"),
    "DieID": ("hardware", "Die ID", "Die ID"),
    "ProductionSOC": ("hardware", "SoC de producción", "Production SoC"),
    "BasebandSerialNumber": ("hardware", "Nº de serie del módem", "Modem serial number"),
    "MLBSerialNumber": ("hardware", "Nº de serie de la placa lógica (MLB)", "Logic board serial number (MLB)"),
    "WiFiAddress": ("network", "MAC WiFi", "Wi-Fi MAC"),
    "BluetoothAddress": ("network", "MAC Bluetooth", "Bluetooth MAC"),
    "EthernetAddress": ("network", "MAC Ethernet", "Ethernet MAC"),
    "SIMStatus": ("network", "Estado de la SIM", "SIM status"),
    "SIMTrayStatus": ("network", "Bandeja SIM", "SIM tray"),
    "TelephonyCapability": ("network", "Tiene telefonía", "Has telephony"),
    "CellularDataCapability": ("network", "Datos móviles", "Cellular data"),
    "BatteryCurrentCapacity": ("battery", "Carga de la batería", "Battery charge"),
    "BatteryIsCharging": ("battery", "Cargando", "Charging"),
    "ExternalChargeCapable": ("battery", "Admite carga externa", "Supports external charging"),
    "ExternalConnected": ("battery", "Cargador conectado", "Charger connected"),
    "FullyCharged": ("battery", "Carga completa", "Fully charged"),
    "GasGaugeCapability": ("battery", "Medidor de batería (gas gauge)", "Battery gauge (gas gauge)"),
    "HasBattery": ("battery", "Tiene batería", "Has battery"),
    "TotalDiskCapacity": ("battery", "Capacidad total", "Total capacity"),
    "TotalSystemCapacity": ("battery", "Partición del sistema", "System partition"),
    "TotalSystemAvailable": ("battery", "Sistema libre", "System free"),
    "TotalDataCapacity": ("battery", "Capacidad de datos", "Data capacity"),
    "TotalDataAvailable": ("battery", "Datos libres", "Data free"),
    "AmountDataReserved": ("battery", "Espacio reservado", "Reserved space"),
    "AmountDataAvailable": ("battery", "Espacio disponible", "Available space"),
    "AmountRestoreAvailable": ("battery", "Espacio para restaurar", "Space for restore"),
    "ActivationState": ("security", "Estado de activación", "Activation state"),
    "ActivationStateAcknowledged": ("security", "Activación confirmada", "Activation acknowledged"),
    "PasswordProtected": ("security", "Código de bloqueo activo", "Passcode enabled"),
    "TrustedHostAttached": ("security", "Equipo de confianza conectado", "Trusted computer attached"),
    "BrickState": ("security", "Dispositivo bloqueado (brick)", "Device bricked"),
    "HasSiDP": ("security", "Tiene SiDP", "Has SiDP"),
    "IsInternalBuild": ("security", "Build interna", "Internal build"),
}
ORDER = {k: i for i, k in enumerate(KEYMAP)}
BYTES_KEYS = {"TotalDiskCapacity", "TotalSystemCapacity", "TotalSystemAvailable", "TotalDataCapacity",
              "TotalDataAvailable", "AmountDataReserved", "AmountDataAvailable", "AmountRestoreAvailable"}
DEFAULT_OFF_CATEGORIES = {"other"}

RECOVERY_NAMES = {
    "MODE": ("Modo", "Mode"), "PRODUCT": ("Identificador de modelo", "Model identifier"),
    "MODEL": ("Modelo de placa", "Board model"), "NAME": ("Nombre", "Name"), "ECID": ("ECID", "ECID"),
    "CPID": ("CPID", "CPID"), "BDID": ("BDID", "BDID"), "IMEI": ("IMEI", "IMEI"),
    "SRNM": ("Nº de serie", "Serial number"), "NONC": ("Nonce", "Nonce"), "SNON": ("Nonce SEP", "SEP nonce"),
}


@dataclass
class Field:
    key: str
    label: str
    category: str
    value: str

    @property
    def category_label(self):
        return category_label(self.category)


def format_value(key, v):
    if isinstance(v, bool):
        return tr("Sí", "Yes") if v else "No"
    if key in BYTES_KEYS and isinstance(v, (int, float)):
        return fmt_bytes(v)
    if key == "BatteryCurrentCapacity":
        return f"{v}%"
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
    else:
        s = str(v)
    return s if len(s) <= 220 else s[:217] + "…"


def flatten(info, extra=None):
    merged = dict(info or {})
    for k, v in (extra or {}).items():
        merged.setdefault(k, v)
    fields = []
    for k, v in merged.items():
        if isinstance(v, (bytes, bytearray)) or v in (None, ""):
            continue
        if k in KEYMAP:
            cat, es, en = KEYMAP[k]
            label = tr(es, en)
        else:
            cat, label = "other", k
        fields.append(Field(k, label, cat, format_value(k, v)))
    fields.sort(key=lambda f: (CATEGORY_ORDER.index(f.category), ORDER.get(f.key, 10_000), f.label.lower()))
    return fields


def from_recovery(rec):
    out = []
    for k, v in rec.items():
        if v and v != "N/A":
            names = RECOVERY_NAMES.get(k)
            out.append(Field(k, tr(*names) if names else k, "recovery", v))
    return out


def group(fields):
    res = {}
    for f in fields:
        res.setdefault(f.category, []).append(f)
    return [(c, res[c]) for c in CATEGORY_ORDER if c in res]
