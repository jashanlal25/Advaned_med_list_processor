"""PDF export for generated MedList orders.

Keep the discount mark as display metadata. Calculations continue to use the
numeric discount in the order payload.
"""

import io
import json
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
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12*mm,
                            rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    normal = ParagraphStyle('normal', fontName='Helvetica', fontSize=8, leading=11)
    bold = ParagraphStyle('bold', parent=normal, fontName='Helvetica-Bold')
    heading = ParagraphStyle('heading', parent=bold, fontSize=16, leading=19)
    right = ParagraphStyle('right', parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle('right_bold', parent=right, fontName='Helvetica-Bold')
    par = lambda value, style=normal: Paragraph(escape(_text(value)), style)

    title = _text(payload.get('shopTitle')) or 'MedList Order'
    date = datetime.now(ZoneInfo('Asia/Karachi')).strftime('%Y-%m-%d %H:%M')
    story = [par(title, heading), par('Date: ' + date),
             par('List No: ' + _text(payload.get('offerId'), 60)),
             par('Name: ' + (_text(payload.get('customerName')) or '—')), Spacer(1, 7*mm)]

    headers = ['Code', 'Item', 'Qty', 'TP', 'Disc%', 'Bonus', 'Tax', 'Net']
    rows = [[par(h, bold) for h in headers]]
    items = payload.get('items') or []
    for item in items:
        if not isinstance(item, dict):
            continue
        rows.append([
            par(item.get('code'), normal),
            par(item.get('name'), normal),
            par(_text(item.get('qty'), 20), right),
            par(f"{_number(item.get('tp')):,.2f}", right),
            par(_discount(item), right),
            par(item.get('bonus') or '—', normal),
            par(f"{_number(item.get('tax')):,.2f}" if _number(item.get('tax')) else '—', right),
            par(f"{_number(item.get('lineNet')):,.2f}", right),
        ])
    if len(rows) == 1:
        raise ValueError('No order items')

    table = Table(rows, colWidths=[14*mm, 55*mm, 11*mm, 23*mm,
                                   23*mm, 17*mm, 17*mm, 24*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef1f7')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.HexColor('#666666')),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#dddddd')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story += [Spacer(1, 5*mm), par('Total Items: ' + str(len(rows)-1), right_bold),
              par('Total: ' + f"{_number(payload.get('netTotal')):,.2f}", right_bold)]
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
