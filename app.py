from flask import Flask, render_template, request, send_file, jsonify, redirect, session
from bs4 import BeautifulSoup
from werkzeug.utils import secure_filename
import os
import io
import re
import sys
import json
import secrets

# Add list_to_htm to path for importing update_htm functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'list_to_htm'))
from update_htm import (
    parse_discount_value, generate_item_row, generate_section_header,
    generate_js_vars_full, generate_js_vars_simple, generate_js_vars_createrows,
    generate_js_if_blocks, generate_js_if_blocks_pdf, generate_js_if_blocks_whatsapp,
    update_htm, generate_html_new_format
)

# Import the search functionality
sys.path.insert(0, os.path.dirname(__file__))
try:
    from search_medicines import MedicineSearcher
except ImportError as e:
    print(f"Error importing search_medicines: {e}")
    MedicineSearcher = None

def decompress_if_needed(data):
    """Auto-detect and decompress gzip data, return original bytes if not compressed."""
    try:
        return gzip_module.decompress(data)
    except (OSError, Exception):
        return data

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static'), static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

from chatbot_bp import chatbot_bp
app.register_blueprint(chatbot_bp)

# UUID-keyed result store. Keys are unguessable tokens returned to the originating
# client — no shared fixed keys that one user could use to read another's data.
RESULT_TTL = 300  # seconds
processed_results = {}  # {token: {'data': ..., 'expires_at': float}}


def _store_result(data: dict) -> str:
    import time as _t
    token = secrets.token_urlsafe(32)
    now = _t.time()
    expired = [k for k, v in processed_results.items() if v['expires_at'] < now]
    for k in expired:
        del processed_results[k]
    processed_results[token] = {'data': data, 'expires_at': now + RESULT_TTL}
    return token


def _get_result(token: str):
    import time as _t
    entry = processed_results.get(token)
    if not entry:
        return None
    if _t.time() > entry['expires_at']:
        del processed_results[token]
        return None
    return entry['data']

def _fmt_tp(text):
    """Strip text to a clean numeric TP string like '2188.75'. Returns '' if non-numeric."""
    if not text:
        return ""
    cleaned = ''.join(ch for ch in text if ch.isdigit() or ch == '.')
    if not cleaned:
        return ""
    try:
        return f"{float(cleaned):.2f}"
    except ValueError:
        return ""

def process_htm_content(html_content, decrease_value=1, stock_format=False, new_format=False, discount_end_mark='keep'):
    """Process HTM content and extract medicine names with discount rates.

    Each result also carries the extra fields needed by the new-format generator:
    code, tp, bonus, tax. Tax defaults to '0.00' when the input does not carry it.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    results = []

    if new_format:
        # New format: <tr class="item-row"> with data-disc/data-bonus attributes .main
        items = soup.find_all("tr", class_="item-row")
        for item in items:
            columns = item.find_all("td")
            if len(columns) < 2:
                continue

            # Name is in td.cell-name (td[1])
            name_td = item.find("td", class_="cell-name")
            medicine_name = (name_td.text.strip() if name_td else columns[1].text.strip()).title()

            # Prefer data-disc attribute; fall back to data-bonus if disc is 0
            disc_attr = item.get("data-disc", "").strip()
            disc_suffix_attr = item.get("data-disc-suffix", "").strip()
            bonus_attr = item.get("data-bonus", "").strip()
            tp_attr = item.get("data-tp", "").strip()
            tax_attr = item.get("data-tax", "").strip()

            try:
                disc_num = float(disc_attr) if disc_attr else 0.0
            except ValueError:
                disc_num = 0.0

            # Detect original ending mark from data-disc-suffix
            original_end_mark = ''
            if disc_suffix_attr and len(disc_suffix_attr) == 1 and disc_suffix_attr in '.,;:':
                original_end_mark = disc_suffix_attr

            if disc_num > 0:
                disc_num -= decrease_value
                disc_num = max(disc_num, 0)

                # Apply ending mark based on user selection
                if discount_end_mark == 'keep':
                    # Keep the original mark (or no mark if there wasn't one)
                    ending = original_end_mark
                elif discount_end_mark == '':
                    # Strip all marks
                    ending = ''
                else:
                    # Apply the selected mark
                    ending = discount_end_mark

                discount_rate = f"{disc_num:.2f}%{ending}"
            elif bonus_attr:
                discount_rate = bonus_attr
            else:
                discount_rate = "0.00%"

            # Code: prefer first <td> text, fall back to data-id stripped of trailing digits
            code = columns[0].text.strip() if columns else ""

            results.append({
                'name': medicine_name,
                'discount': discount_rate,
                'code': code,
                'tp': _fmt_tp(tp_attr),
                'bonus': bonus_attr,
                'tax': _fmt_tp(tax_attr) or "0.00",
            })

    else:
        # Default / stock format: <tr class="item">
        items = soup.find_all("tr", class_="item")
        # Column layouts differ:
        #   Stock format:  [SR#, Code, Name, Disc%, T.P, Box, Pcs, Cost, Amount]
        #   Default offer: [Code, Name, Order(qty), Disc%, Bonus, T.P (colspan=2)]
        if stock_format:
            name_index, code_index, disc_index = 2, 1, 3
            tp_index, bonus_index, tax_index = 4, None, None
        else:
            name_index, code_index, disc_index = 1, 0, 3
            bonus_index = 4
            # Auto-detect TP and Tax columns by checking first item row column count:
            #   5 cols → basic old (no TP, no Tax)
            #   6 cols → old with TP, no Tax
            #   7 cols → old with TP + Tax
            first_item = items[0] if items else None
            first_cols = len(first_item.find_all("td")) if first_item else 6
            if first_cols >= 7:
                tp_index, tax_index = 5, 6
            elif first_cols >= 6:
                tp_index, tax_index = 5, None
            else:
                tp_index, tax_index = None, None

        for item in items:
            columns = item.find_all("td")
            if len(columns) >= 4:
                # Extract medicine name and apply title case
                medicine_name = columns[name_index].text.strip().title()
                discount_rate = columns[disc_index].text.strip()
                code = columns[code_index].text.strip() if code_index < len(columns) else ""
                bonus_text = (columns[bonus_index].text.strip()
                              if bonus_index is not None and bonus_index < len(columns)
                              else "")
                tp_text = (columns[tp_index].text.strip()
                           if tp_index is not None and tp_index < len(columns)
                           else "")
                tax_text = (columns[tax_index].text.strip()
                            if tax_index is not None and tax_index < len(columns)
                            else "0.00")

                # Check if discount is 0.00% and get bonus rate if available
                if discount_rate == "0.00%" and len(columns) >= 5:
                    discount_rate = columns[4].text.strip()

                # Extract numeric part and any additional separators
                original_discount = discount_rate
                percent_pos = original_discount.find('%')

                if percent_pos != -1:
                    # Has a percentage - extract numeric part and detect ending mark
                    num_part = original_discount[:percent_pos+1]  # Include the %
                    after_percent = original_discount[percent_pos+1:].strip()

                    # Detect original ending mark
                    original_end_mark = ''
                    if after_percent and len(after_percent) == 1 and after_percent in '.,;:':
                        original_end_mark = after_percent

                    try:
                        rate_value = float(num_part.strip('%'))
                        rate_value -= decrease_value
                        rate_value = max(rate_value, 0)

                        # Apply ending mark based on user selection
                        if discount_end_mark == 'keep':
                            # Keep the original mark (or no mark if there wasn't one)
                            ending = original_end_mark
                        elif discount_end_mark == '':
                            # Strip all marks
                            ending = ''
                        else:
                            # Apply the selected mark
                            ending = discount_end_mark

                        discount_rate = f"{rate_value:.2f}%{ending}"
                    except ValueError:
                        # If conversion fails, keep the original
                        discount_rate = original_discount
                else:
                    # No percentage found, treat as special case (like TP, NET, etc.)
                    try:
                        # Check if it's a numeric value without %
                        rate_value = float(original_discount)
                        rate_value -= decrease_value
                        rate_value = max(rate_value, 0)
                        discount_rate = f"{rate_value:.2f}"  # No % since original had none
                    except ValueError:
                        # Keep original value if it's not numeric
                        discount_rate = original_discount

                results.append({
                    'name': medicine_name,
                    'discount': discount_rate,
                    'code': code,
                    'tp': _fmt_tp(tp_text),
                    'bonus': bonus_text,
                    'tax': _fmt_tp(tax_text) or "0.00",
                })

    return results

def generate_text_output(results, separator=',', extended=False):
    """Generate text file content from results.

    extended=False -> 'Name----- Disc%,'  (legacy, byte-compatible with old behaviour)
    extended=True  -> 'Name----- Disc%|tp|bonus|tax'  (no trailing separator)
    """
    lines = []
    for item in results:
        discount = item['discount']
        if extended:
            tp = item.get('tp', '') or ''
            bonus = item.get('bonus', '') or ''
            tax = item.get('tax', '') or '0.00'
            disc_field = f"{discount}{separator}" if separator and not discount.endswith(separator) else discount
            output_line = f"{item['name']}----- {disc_field}|{tp}|{bonus}|{tax}"
        else:
            if separator and not discount.endswith(separator):
                output_line = f"{item['name']}----- {discount}{separator}"
            else:
                output_line = f"{item['name']}----- {discount}"
        lines.append(output_line)
    return '\n'.join(lines)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/share', methods=['POST', 'GET'])
def share():
    # Handle share target from PWA
    return redirect('/?shared=true')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith(('.htm', '.html')):
        return jsonify({'error': 'Please upload an HTM or HTML file'}), 400

    # Get decrease value from form (default to 1 if not provided)
    try:
        decrease_value = float(request.form.get('decrease_value', 0))
    except ValueError:
        decrease_value = 0

    # Get separator from form (default to comma)
    separator = request.form.get('separator', ',')

    # Get stock format checkbox (default to False)
    stock_format = request.form.get('stock_format', 'false').lower() == 'true'

    # Get new format checkbox (default to False)
    new_format = request.form.get('new_format', 'false').lower() == 'true'

    # Output format: 'old' (default, name+disc only) or 'extended' (with code|tp|bonus|tax)
    output_format = request.form.get('output_format', 'old').lower()
    extended_output = output_format == 'extended'

    # Get discount ending mark preference (default to 'keep')
    discount_end_mark = request.form.get('discount_end_mark', 'keep')

    try:
        try:
            html_content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            file.seek(0)
            html_content = file.read().decode('latin-1')

        results = process_htm_content(html_content, decrease_value, stock_format, new_format, discount_end_mark)
        text_output = generate_text_output(results, separator, extended=extended_output)

        filename_base = os.path.splitext(secure_filename(file.filename))[0]
        output_filename = f"{filename_base}_name_with_%.txt"
        token = _store_result({
            'text': text_output,
            'filename': output_filename,
            'results': results
        })

        return jsonify({
            'success': True,
            'results': results,
            'text_output': text_output,
            'filename': output_filename,
            'download_token': token,
            'count': len(results),
            'decrease_value': decrease_value
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            'error': f'Error processing file: {str(e)}',
            'details': error_details
        }), 500

@app.route('/download')
def download_file():
    data = _get_result(request.args.get('token', ''))
    if not data:
        return "No file to download or token expired", 404

    buffer = io.BytesIO()
    buffer.write(data['text'].encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=data['filename'],
        mimetype='text/plain'
    )

# ============ MAKE HTML FILE FUNCTIONALITY ============

def parse_text_content(text_content):
    """Parse text content (data.txt format) and return list of (item_name, discount_or_bonus).

    Accepts both legacy lines ('Name----- 7%') and extended lines
    ('code|Name----- 7%|tp|bonus|tax'). Only the name/value pair is returned —
    callers that need the extended fields should use parse_text_content_extended().
    """
    items = []
    for line in text_content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '→' in line:
            line = line.split('→', 1)[1]
        # If the line is in extended format, strip to just the name----- value part.
        if '|' in line:
            parts_pipe = line.split('|')
            if len(parts_pipe) >= 2 and '-----' in parts_pipe[0]:
                # "name----- value | tp | bonus | tax" — keep only name-value part
                line = parts_pipe[0]
            elif len(parts_pipe) >= 2 and '-----' in parts_pipe[1]:
                # legacy: "code | name----- value | ..."
                line = parts_pipe[1]
        if '-----' in line:
            parts = line.split('-----')
            item_name = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ''
            value = value.strip()
            # Strip trailing separators (',' / ';') that the writer added.
            while value and value[-1] in ',;':
                value = value[:-1].rstrip()
            items.append((item_name, value))
    return items

def parse_text_content_extended(text_content):
    """Parse text content and return a list of dicts with all fields.

    Each dict has: name, value, tp, bonus, tax.
    Format: 'Name----- Disc%|tp|bonus|tax'
    Legacy lines (without '|') still parse: tp/bonus default empty, tax='0.00'.
    """
    items = []
    for line in text_content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '→' in line:
            line = line.split('→', 1)[1]

        tp, bonus, tax = "", "", "0.00"

        if '|' in line:
            parts_pipe = line.split('|')
            # Layout: name----- disc% | tp | bonus | tax
            name_value_part = parts_pipe[0]
            if len(parts_pipe) > 1:
                tp = parts_pipe[1].strip()
            if len(parts_pipe) > 2:
                bonus = parts_pipe[2].strip()
            if len(parts_pipe) > 3 and parts_pipe[3].strip():
                tax = parts_pipe[3].strip()
            line_for_namevalue = name_value_part
        else:
            line_for_namevalue = line

        if '-----' not in line_for_namevalue:
            continue

        name_part, _, value_part = line_for_namevalue.partition('-----')
        name = name_part.strip()
        value = value_part.strip()

        items.append({
            'name': name,
            'value': value,
            'tp': tp,
            'bonus': bonus,
            'tax': tax,
        })
    return items

def generate_html_from_template(data_items, template_path, list_no="000001", list_date=None, title="S.S.D PHARMA", whatsapp_number="923337068868", preserve_end_marks=False):
    """Generate HTML file from template and data items"""
    import datetime
    if list_date is None:
        list_date = datetime.datetime.now().strftime("%d/%m/%Y")

    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()

    total_count = len(data_items)

    # Replace title everywhere
    content = content.replace('S.S.D PHARMA', title)

    # Replace WhatsApp number everywhere
    content = content.replace('923337068868', whatsapp_number)
    content = content.replace('%2B923337068868', '%2B' + whatsapp_number)

    # 1. Replace "Code" header with "Sr#"
    content = re.sub(
        r'(<td style="text-align: center; border-radius: 16px 0px 0px 0px;">)(Code|Sr#)(</td>)',
        r'\1Sr#\3',
        content
    )

    # 2. Update tbody
    tbody_start = content.find('<tbody id="myTable">')
    tbody_end = content.find('</tbody>')

    if tbody_start == -1 or tbody_end == -1:
        return None, "ERROR: Could not find tbody section in template"

    # Sort items alphabetically by name
    sorted_items = sorted(data_items, key=lambda x: x[0].upper() if x[0] else "")

    items_html = ""
    current_letter = ""
    for i, (item_name, value) in enumerate(sorted_items, 1):
        first_letter = item_name[0].upper() if item_name else "?"
        if first_letter != current_letter:
            current_letter = first_letter
            items_html += generate_section_header(current_letter)
        items_html += generate_item_row(i, item_name, value, preserve_end_marks)

    items_html += f'''<tr class="heading2"> <td style=" text-align: CENTER; border-radius: 0px 0px 16px 16px; padding-left: 10px;" colspan="5" >Total Products :
  {total_count}
</td></tr>
'''

    content = content[:tbody_start + len('<tbody id="myTable">')] + items_html + content[tbody_end:]

    # 3. Update list number and date
    content = re.sub(r'<b>List No : </b>\s*\d+', f'<b>List No : </b>\n{list_no}', content)
    content = re.sub(r'<b>List Date </b> :\s*[\d/]+', f'<b>List Date </b> :\n{list_date}', content)

    # Update global list number variable for PDF generator
    content = re.sub(r'var LISTNO_GLOBAL = "[^"]*";', f'var LISTNO_GLOBAL = "{list_no}";', content)

    # Update global WhatsApp number variable
    content = re.sub(r'var WHATSAPP_GLOBAL = "[^"]*";', f'var WHATSAPP_GLOBAL = "{whatsapp_number}";', content)

    # 4. Update hidden inputs for rows count
    content = re.sub(r'id="rows" value="\d+"', f'id="rows" value="{total_count}"', content)

    # 5. Generate new JS content
    js_vars_full = generate_js_vars_full(sorted_items, preserve_end_marks)
    js_vars_simple = generate_js_vars_simple(sorted_items, preserve_end_marks)
    js_if_blocks_printf = generate_js_if_blocks(sorted_items, 'mywindow')
    js_if_blocks_myfun = generate_js_if_blocks(sorted_items, 'myWindow')
    js_if_whatsapp = generate_js_if_blocks_whatsapp(sorted_items)

    # 6. Update Printf function
    content = re.sub(
        r'(function Printf\(\)\{\nvar ITDATE = ")[^"]*(";\nvar LSTNO = ")[^"]*(")',
        r'\g<1>' + list_date + r'\g<2>' + list_no + r'\g<3>',
        content
    )
    content = re.sub(
        r'(function Printf\(\)\{\nvar ITDATE = "[^"]*";\nvar LSTNO = "[^"]*";\nvar custname = document\.getElementById\("cstname"\)\.value;\nvar serial = 0;\n)'
        r'.*?'
        r'(\n\n\n var mywindow = window\.open)',
        r'\1' + js_vars_full + r'\2',
        content,
        flags=re.DOTALL
    )

    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\n mywindow\.document\.write\('<tr class=\"item\">.*?"
        r"( mywindow\.document\.write\('<tr class=\"heading2\"> <td)",
        js_if_blocks_printf + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    # 7. Update mywht function
    content = re.sub(
        r'(function mywht\(\)\{\nvar ITDATE = ")[^"]*(";\nvar LSTNO = ")[^"]*(")',
        r'\g<1>' + list_date + r'\g<2>' + list_no + r'\g<3>',
        content
    )
    content = re.sub(
        r'(function mywht\(\)\{.*?var serial = 0;\n)'
        r'.*?'
        r'(\nvar url="https://wa\.me)',
        r'\1' + js_vars_simple + '\n' + js_if_whatsapp + r'\2',
        content,
        flags=re.DOTALL
    )

    # 8. Update myfun function
    content = re.sub(
        r'(function myfun\(\)\{\nvar ITDATE = ")[^"]*(";\nvar LSTNO = ")[^"]*(")',
        r'\g<1>' + list_date + r'\g<2>' + list_no + r'\g<3>',
        content
    )
    content = re.sub(
        r'(function myfun\(\)\{\nvar ITDATE = "[^"]*";\nvar LSTNO = "[^"]*";\nvar custname = document\.getElementById\("cstname"\)\.value;\nvar serial = 0;\n)'
        r'.*?'
        r'(\nmyWindow=window\.open)',
        r'\1' + js_vars_full + r'\2',
        content,
        flags=re.DOTALL
    )

    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\n myWindow\.document\.write\('<tr class=\"item\">.*?"
        r"( myWindow\.document\.write\('<tr class=\"heading2\"> <td)",
        js_if_blocks_myfun + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    # 9. Update createRows function (PDF generation)
    js_vars_createrows = generate_js_vars_createrows(sorted_items, preserve_end_marks)
    js_if_blocks_pdf = generate_js_if_blocks_pdf(sorted_items)

    content = re.sub(
        r'(function createRows\(count\) \{\n  const rows = \[\];\n\n)'
        r'.*?'
        r'(var serial = 0;)',
        r'\1' + js_vars_createrows + r'\2',
        content,
        flags=re.DOTALL
    )

    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\nrows\.push.*?"
        r"(\nvar totitem=)",
        js_if_blocks_pdf + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    # 10. Update simpleOrder function item count
    content = re.sub(r'for \(let i = 1; i <= \d+; i\+\+\)', f'for (let i = 1; i <= {total_count}; i++)', content)

    return content, None

@app.route('/make-html')
def make_html_page():
    return render_template('make_html.html')

@app.route('/generate-html', methods=['POST'])
def generate_html():
    try:
        return _generate_html_inner()
    except Exception as exc:
        import traceback
        return jsonify({'error': f'Server error: {type(exc).__name__}: {exc}',
                        'detail': traceback.format_exc()}), 500

def _generate_html_inner():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith(('.txt', '.md', '.text')):
        return jsonify({'error': 'Please upload a text file (.txt)'}), 400

    # Sanitise inputs that get embedded into generated HTML/JS
    list_no = re.sub(r'[^A-Za-z0-9\-_]', '', request.form.get('list_no', '000001'))[:20] or '000001'
    list_date = request.form.get('list_date', None)
    title = re.sub(r'[<>"\'&]', '', request.form.get('title', 'S.S.D PHARMA'))[:80] or 'S.S.D PHARMA'
    whatsapp_number = request.form.get('whatsapp_number', '923337068868')
    message = re.sub(r'<[^>]*>', '', request.form.get('message', ''))[:500]
    list_type = request.form.get('list_type', 'M')
    if list_type not in ('M', 'C'):
        list_type = 'M'
    output_format = request.form.get('output_format', 'old').lower()
    if output_format not in ('old', 'new', 'both'):
        output_format = 'old'
    whatsapp_number = ''.join(filter(str.isdigit, whatsapp_number))

    # Get preserve_end_marks option
    preserve_end_marks = request.form.get('preserve_end_marks', '0') == '1'

    try:
        text_content = file.read().decode('utf-8')
    except UnicodeDecodeError:
        file.seek(0)
        text_content = file.read().decode('latin-1')

    # Parse text content (legacy tuples, used by the old generator)
    data_items = parse_text_content(text_content)

    if not data_items:
        return jsonify({'error': 'No valid items found in the file. Format should be: item_name----- discount%'}), 400

    base_dir = os.path.dirname(__file__)
    template_path_old = os.path.join(base_dir, 'list_to_htm', 'list.HTM')
    template_path_new = os.path.join(base_dir, 'list_to_htm', 'list_new.HTM')

    # Use first word of title (uppercase) as filename prefix: "SSD MEDICOS" → "SSD"
    title_prefix = re.sub(r'[^a-zA-Z0-9]', '', title.split()[0]).upper() if title.strip() else 'OFFER_LIST'

    response_payload = {
        'success': True,
        'count': len(data_items),
        'output_format': output_format,
    }

    # ---- OLD format ----
    if output_format in ('old', 'both'):
        if not os.path.exists(template_path_old):
            return jsonify({'error': 'Old-format template file not found'}), 500
        html_old, err_old = generate_html_from_template(
            data_items, template_path_old, list_no, list_date, title, whatsapp_number, preserve_end_marks
        )
        if err_old:
            return jsonify({'error': err_old}), 500
        old_filename = f"{title_prefix}_{list_type}{list_no}.htm"
        old_token = _store_result({
            'content': html_old, 'filename': old_filename, 'count': len(data_items),
        })
        response_payload['old_filename'] = old_filename
        response_payload['old_token'] = old_token

    # ---- NEW format ----
    if output_format in ('new', 'both'):
        if not os.path.exists(template_path_new):
            return jsonify({'error': 'New-format template file not found'}), 500
        items_extended = parse_text_content_extended(text_content)
        if not items_extended:
            return jsonify({'error': 'No valid items for new format'}), 400
        has_pipe_data = '|' in text_content
        if has_pipe_data and not any((it.get('tp') or '').strip() for it in items_extended):
            return jsonify({
                'error': 'New format needs T.P values. Re-export your TXT in '
                         '"Extended TXT" mode from the home page (or include code|name|tp|bonus|tax).'
            }), 400
        html_new, err_new = generate_html_new_format(
            template_path_new, items_extended, list_no, list_date, title, whatsapp_number, message
        )
        if err_new:
            return jsonify({'error': err_new}), 500
        new_filename = f"{title_prefix}_{list_type}{list_no}_new.htm"
        new_token = _store_result({
            'content': html_new, 'filename': new_filename, 'count': len(items_extended),
        })
        response_payload['new_filename'] = new_filename
        response_payload['new_token'] = new_token

    response_payload['filename'] = (
        response_payload.get('old_filename') or response_payload.get('new_filename')
    )
    response_payload['message'] = f'Generated {output_format} format with {len(data_items)} items'
    return jsonify(response_payload)

def _send_html_payload():
    data = _get_result(request.args.get('token', ''))
    if not data:
        return "No file to download or token expired", 404
    buffer = io.BytesIO()
    buffer.write(data['content'].encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=data['filename'], mimetype='text/html')

@app.route('/download-html')
def download_html():
    return _send_html_payload()

@app.route('/download-html-new')
def download_html_new():
    return _send_html_payload()

@app.route('/preview-html')
def preview_html():
    data = _get_result(request.args.get('token', ''))
    if not data:
        return "No HTML generated yet or token expired.", 404
    return data['content']

@app.route('/preview-html-new')
def preview_html_new():
    data = _get_result(request.args.get('token', ''))
    if not data:
        return "No new-format HTML generated yet or token expired.", 404
    return data['content']

# ============ SEARCH MEDICINES FUNCTIONALITY ============

@app.route('/search')
def search_page():
    return render_template('search.html')


@app.route('/diff')
def diff_page():
    return render_template('diff.html')

import atexit
import shutil
import tempfile
import gzip as gzip_module
import time

SESSION_TTL = 4 * 3600  # 4 hours in seconds

# Global instance to store uploaded files: {session_id: {'files': [...], 'expires_at': timestamp}}
uploaded_files_storage = {}

def purge_expired_sessions():
    """Remove sessions that have passed their 5-minute TTL."""
    now = time.time()
    expired = [sid for sid, data in uploaded_files_storage.items() if data['expires_at'] < now]
    for sid in expired:
        del uploaded_files_storage[sid]

def cleanup_uploads():
    """Clean up uploaded files when the application stops"""
    upload_dir = os.path.join(tempfile.gettempdir(), 'medicine_uploads')
    if os.path.exists(upload_dir):
        # Clean all files in the uploads directory
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')

# Register cleanup function to run on exit
atexit.register(cleanup_uploads)

def _session_dir(session_id):
    """Return the on-disk folder for a session."""
    base = os.path.join(tempfile.gettempdir(), 'medicine_uploads')
    # Sanitise session_id so it is safe as a directory name
    safe_sid = re.sub(r'[^A-Za-z0-9_\-]', '', session_id)[:64]
    return os.path.join(base, safe_sid)

def _reconstruct_session(session_id):
    """Re-populate uploaded_files_storage from disk if folder exists and is fresh."""
    folder = _session_dir(session_id)
    if not os.path.isdir(folder):
        return False
    # Use folder mtime as a proxy for last-upload time
    age = time.time() - os.path.getmtime(folder)
    if age > SESSION_TTL:
        shutil.rmtree(folder, ignore_errors=True)
        return False
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.isfile(os.path.join(folder, f))]
    if not files:
        return False
    uploaded_files_storage[session_id] = {
        'files': files,
        'expires_at': time.time() + (SESSION_TTL - age)
    }
    return True

@app.route('/upload-lists', methods=['POST'])
def upload_lists():
    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('files')

    # session_id: reuse existing or create new
    client_sid = request.form.get('session_id', '').strip()
    purge_expired_sessions()
    if client_sid and (client_sid in uploaded_files_storage or _reconstruct_session(client_sid)):
        session_id = client_sid
    else:
        session_id = secrets.token_urlsafe(32)
        uploaded_files_storage[session_id] = {'files': [], 'expires_at': 0}

    folder = _session_dir(session_id)
    os.makedirs(folder, exist_ok=True)

    file_paths = []
    for file in files:
        if file.filename == '':
            continue
        if not file.filename.lower().endswith(('.htm', '.html', '.txt', '.text', '.pdf')):
            continue
        filename = secure_filename(file.filename) or 'upload'
        filepath = os.path.join(folder, filename)
        file_data = decompress_if_needed(file.read())
        with open(filepath, 'wb') as f:
            f.write(file_data)
        file_paths.append(filepath)

    # Touch folder mtime so age tracking stays current
    os.utime(folder, None)

    uploaded_files_storage[session_id]['files'] = [
        os.path.join(folder, f) for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
    ]
    uploaded_files_storage[session_id]['expires_at'] = time.time() + SESSION_TTL

    total_files_for_session = len(uploaded_files_storage[session_id]['files'])
    return jsonify({
        'success': True,
        'message': f'Uploaded {len(file_paths)} files, total files in session: {total_files_for_session}',
        'session_id': session_id,
        'expires_in': SESSION_TTL
    })

@app.route('/remove-file', methods=['POST'])
def remove_file():
    data = request.get_json()
    session_id = (data.get('session_id') or '').strip()
    filename = (data.get('filename') or '').strip()

    if not session_id or not filename:
        return jsonify({'error': 'session_id and filename required'}), 400

    session_data = uploaded_files_storage.get(session_id)
    if not session_data:
        _reconstruct_session(session_id)
        session_data = uploaded_files_storage.get(session_id)
    if not session_data:
        return jsonify({'error': 'Session not found'}), 404

    files = session_data['files']
    match = next((p for p in files if os.path.basename(p) == filename), None)
    if not match:
        return jsonify({'error': 'File not found in session'}), 404

    files.remove(match)
    try:
        os.unlink(match)
    except OSError:
        pass

    return jsonify({'success': True, 'remaining': len(files)})

@app.route('/search-medicines', methods=['POST'])
def search_medicines():
    data = request.get_json()
    search_terms = data.get('search_terms', [])
    session_id = (data.get('session_id') or '').strip()

    if not search_terms:
        return jsonify({'error': 'No search terms provided'}), 400

    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400

    # Get file paths for this session, checking expiry
    # Try to reconstruct from disk if server was restarted
    session_data = uploaded_files_storage.get(session_id)
    if not session_data:
        if not _reconstruct_session(session_id):
            return jsonify({'error': 'Session expired or no files uploaded. Please upload your files again.', 'expired': True}), 400
        session_data = uploaded_files_storage[session_id]
    if time.time() > session_data['expires_at']:
        del uploaded_files_storage[session_id]
        shutil.rmtree(_session_dir(session_id), ignore_errors=True)
        return jsonify({'error': 'Session expired. Please upload your files again.', 'expired': True}), 400
    file_paths = session_data['files']
    if not file_paths:
        return jsonify({'error': 'No files uploaded for this session'}), 400

    # Check if MedicineSearcher is available
    if MedicineSearcher is None:
        return jsonify({'error': 'Search functionality not available, unable to import required modules'}), 500

    # Perform the search
    searcher = MedicineSearcher()
    results = searcher.search_medicines(file_paths, search_terms)

    return jsonify({
        'success': True,
        'results': results,
        'total_files': len(file_paths),
        'total_matches': sum(len(result['matches']) for result in results)
    })

if __name__ == '__main__':
    # host='0.0.0.0' allows access from other devices on same network
    app.run(debug=True, host='0.0.0.0', port=5001)
