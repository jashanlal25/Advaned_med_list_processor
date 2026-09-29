"""PDF export for generated MedList orders.

Keep the discount mark as display metadata. Calculations continue to use the
numeric discount in the order payload.
"""

import io
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request, send_file

order_pdf = Blueprint('order_pdf', __name__)


def _text(value, limit=140):
    return str(value if value is not None else '')[:limit].strip()


def _number(value):
    try:
        result = float(value)
        if not (-1e12 < result < 1e12):
            return 0.0
        return result
    except (ValueError, TypeError):
        return 0.0


def _discount(item):
    rate = _number(item.get('disc'))
    suffix = _text(item.get('discSuffix'), 24)
    # Suffix is presentation data, never part of the numeric calculation.
    return f'{rate:.2f}%{suffix}' if rate else '—'


def _pdf(payload):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    # ReportLab ships these fonts, so the bill looks consistent on Android PDF viewers.
    font_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
    if 'MedListVera' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('MedListVera', os.path.join(font_dir, 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('MedListVeraBold', os.path.join(font_dir, 'VeraBd.ttf')))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=8*mm,
                            rightMargin=8*mm, topMargin=8*mm, bottomMargin=8*mm)
    normal = ParagraphStyle('normal', fontName='MedListVera', fontSize=7, leading=9)
    bold = ParagraphStyle('bold', parent=normal, fontName='MedListVeraBold')
    heading = ParagraphStyle('heading', parent=bold, fontSize=14, leading=17)
    right = ParagraphStyle('right', parent=normal, alignment=TA_RIGHT)
    center = ParagraphStyle('center', parent=normal, alignment=TA_CENTER)
    par = lambda value, style=normal: Paragraph(escape(_text(value)), style)

    title = _text(payload.get('shopTitle')) or 'MedList Order'
    date = datetime.now(ZoneInfo('Asia/Karachi')).strftime('%Y-%m-%d %H:%M')
    story = [par(title, heading), par('Date: ' + date),
             par('Name: ' + (_text(payload.get('customerName')) or '—'), bold),
             Spacer(1, 5*mm)]

    items = [item for item in (payload.get('items') or []) if isinstance(item, dict)]
    if not items:
        raise ValueError('No order items')
    show_bonus = any(_text(item.get('bonus')) for item in items)
    show_tax = any(_number(item.get('tax')) for item in items)
    headers = ['Code', 'Item', 'Qty', 'TP', 'Disc%']
    if show_bonus:
        headers.append('Bonus')
    if show_tax:
        headers.append('Tax')
    headers.append('Net')
    rows = [[par(h, bold) for h in headers]]
    for item in items:
        row = [
            par(item.get('code'), normal),
            par(_text(item.get('name')).lower(), normal),
            par(_text(item.get('qty'), 20), right),
            par(f"{_number(item.get('tp')):,.2f}", right),
            par(_discount(item), right),
        ]
        if show_bonus:
            row.append(par(item.get('bonus') or '—', center))
        if show_tax:
            row.append(par(f"{_number(item.get('tax')):,.2f}" if _number(item.get('tax')) else '—', right))
        row.append(par(f"{_number(item.get('lineNet')):,.2f}", right))
        rows.append(row)

    # The original Anas bill keeps counts and totals inside the bordered table.
    empty = [''] * (len(headers) - 3)
    rows.append(empty + [par('Total Items', right), '', par(str(len(items)), right)])
    rows.append(empty + [par('Total', right), '',
                         par(f"{_number(payload.get('netTotal')):,.2f}", right)])
    width = A4[0] - 20*mm
    if show_bonus and show_tax:
        ratios = [45, 157, 36, 72, 60, 51, 44, 74]
    elif show_bonus or show_tax:
        ratios = [50, 190, 40, 78, 67, 48, 65]
    else:
        ratios = [59, 244, 47, 75, 70, 44]
    col_widths = [width * n / sum(ratios) for n in ratios]
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f5fa')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cfd2d7')),
        ('SPAN', (0, -2), (-4, -2)),
        ('SPAN', (-3, -2), (-2, -2)),
        ('SPAN', (0, -1), (-4, -1)),
        ('SPAN', (-3, -1), (-2, -1)),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.8),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return buf


@order_pdf.route('/order/pdf', methods=['POST'])
def export_order_pdf():
    raw = request.form.get('payload', '')
    if not raw or len(raw) > 1_000_000:
        return Response('Missing or oversized order payload', status=400)
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
            raise ValueError('Invalid order')
        if len(payload['items']) > 3000:
            raise ValueError('Too many items')
        buf = _pdf(payload)
    except (ValueError, TypeError) as exc:
        return Response('Invalid order payload: ' + str(exc), status=400)
    list_no = re.sub(r'[^A-Za-z0-9_-]', '', _text(payload.get('offerId'), 60)) or 'order'
    response = send_file(buf, mimetype='application/pdf', as_attachment=False,
                         download_name=f'{list_no}-order.pdf')
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-store'
    return response
