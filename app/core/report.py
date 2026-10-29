import html
from datetime import datetime

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from .. import assets
from .. import privacy
from ..i18n import tr
from . import infomap

ACCENT = "#0b7a53"


def _e(s):
    return html.escape(str(s))


def build_html(meta, groups, apps=None, show_keys=False):
    now = datetime.now().strftime(tr("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"))
    logo = ""
    if meta.get("logo"):
        logo = f'<img src="{_e(meta["logo"])}" height="48"> &nbsp; '
    brand = (f'<img src="{_e(assets.path("banner.png"))}" height="40">' if assets.exists("banner.png") else
             f'<span style="font-size:18pt; font-weight:bold; color:{ACCENT};">VeyloraDevice</span>')
    head = (
        f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td>{logo}{brand}</td>'
        f'<td align="right"><span style="font-size:15pt; font-weight:bold;">'
        f'{_e(tr("INFORME DEL DISPOSITIVO", "DEVICE REPORT"))}</span><br>'
        f'<span style="color:#666666;">{now}</span></td></tr></table>'
        f'<hr>'
    )
    people_html = ""

    body = []
    for cat, fields in groups:
        if not fields:
            continue
        rows = []
        for i, f in enumerate(fields):
            bg = "#f3f6f5" if i % 2 == 0 else "#ffffff"
            key = f'<br><span style="color:#999999; font-size:7pt;">{_e(f.key)}</span>' if show_keys else ""
            rows.append(
                f'<tr bgcolor="{bg}"><td width="38%" style="padding:4px;"><b>{_e(f.label)}</b>{key}</td>'
                f'<td style="padding:4px;">{_e(privacy.report_value(f.label, f.value))}</td></tr>')
        body.append(
            f'<h3 style="color:{ACCENT}; margin-top:14px; margin-bottom:4px;">{_e(infomap.category_label(cat))}</h3>'
            f'<table width="100%" cellspacing="0" cellpadding="4">{"".join(rows)}</table>')

    if apps:
        rows = []
        for i, a in enumerate(apps):
            bg = "#f3f6f5" if i % 2 == 0 else "#ffffff"
            rows.append(
                f'<tr bgcolor="{bg}"><td style="padding:3px;">{_e(a.get("name", ""))}</td>'
                f'<td style="padding:3px;">{_e(a.get("id", ""))}</td>'
                f'<td style="padding:3px;">{_e(a.get("version", ""))}</td></tr>')
        body.append(
            f'<h3 style="color:{ACCENT}; margin-top:14px; margin-bottom:4px;">{_e(tr("Aplicaciones instaladas", "Installed apps"))} ({len(apps)})</h3>'
            f'<table width="100%" cellspacing="0" cellpadding="3">'
            f'<tr bgcolor="{ACCENT}"><td><font color="#ffffff"><b>{_e(tr("Nombre", "Name"))}</b></font></td>'
            f'<td><font color="#ffffff"><b>{_e(tr("Identificador", "Identifier"))}</b></font></td>'
            f'<td><font color="#ffffff"><b>{_e(tr("Versión", "Version"))}</b></font></td></tr>{"".join(rows)}</table>')

    notes = ""
    if meta.get("notes", "").strip():
        notes = (f'<h3 style="color:{ACCENT}; margin-top:14px; margin-bottom:4px;">{_e(tr("Observaciones", "Notes"))}</h3>'
                 f'<p>{_e(meta["notes"]).replace(chr(10), "<br>")}</p>')

    foot = f'<hr><p style="color:#888888; font-size:8pt;">{_e(tr("Generado con VeyloraDevice · VeyloraLabs", "Generated with VeyloraDevice · VeyloraLabs"))}</p>'
    return (f'<html><body style="font-family:sans-serif; font-size:10pt;">{head}{people_html}'
            f'{"".join(body)}{notes}{foot}</body></html>')


def write_pdf(path, html_text):
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    writer.setTitle(tr("Informe del dispositivo", "Device report"))
    writer.setResolution(96)
    doc = QTextDocument()
    doc.setHtml(html_text)
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print_(writer)
