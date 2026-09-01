import re

def parse_data_txt(filepath):
    """Parse data.txt and return list of (item_name, discount_or_bonus)"""
    items = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if '→' in line:
                line = line.split('→', 1)[1]
            if '-----' in line:
                parts = line.split('-----')
                item_name = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ''
                items.append((item_name, value))
    return items

def _is_suffix_only(s):
    """True if string is purely trailing punctuation like ',' or '.' — not real bonus info."""
    return bool(s) and all(c in ',.;: ' for c in s.strip())

def parse_discount_value(value, preserve_end_marks=False):
    """Parse discount/bonus value and return (discount_num, bonus_str, end_mark)

    The '/' character is used as a separator between discount and bonus.
    Examples:
        - "10%/5+5" → discount=10.0, bonus="5+5", end_mark=""
        - "TP,/something" → discount=0.0, bonus="TP,/something", end_mark=""
        - "15" → discount=15.0, bonus="", end_mark=""
        - "10.00%." → discount=10.0, bonus="", end_mark="." (if preserve_end_marks=True)
    """
    # First, check if '/' is used as separator for bonus
    bonus_part = ""
    main_value = value
    end_mark = ""

    if '/' in value:
        slash_pos = value.find('/')
        main_value = value[:slash_pos].strip()
        bonus_part = value[slash_pos+1:].strip()

    # Check if it's a "NET" value (e.g. "360 Net" means net rate, not discount%)
    if 'net' in main_value.lower():
        # The number is the NET RATE (TP), not a discount percentage → disc = 0%
        return 0.0, main_value.strip() if not bonus_part else bonus_part, end_mark

    elif '%' in main_value:
        # Extract numeric part from percentage
        percent_pos = main_value.find('%')
        num_part = main_value[:percent_pos]  # Before the % sign
        num = num_part.strip()
        try:
            discount = float(num)
        except:
            discount = 0.0
        # If there's content after % in main_value (before /), check if it's an end mark
        after_percent = main_value[percent_pos+1:]

        if preserve_end_marks and after_percent and len(after_percent) == 1 and after_percent in '.,;:':
            # This is an ending mark to preserve
            end_mark = after_percent
            after_percent = ""
        else:
            after_percent = after_percent.strip()

        if bonus_part:
            # '/' was used, so bonus_part is the bonus
            return discount, bonus_part, end_mark
        elif after_percent:
            # No '/', but there's text after % - treat as additional info
            return discount, after_percent, end_mark
        else:
            return discount, "", end_mark
    elif 'TP' in main_value.upper():
        # Return TP value (preserving any separators like "TP," or "Tp,")
        # If bonus_part exists, combine main_value with bonus info
        if bonus_part:
            return 0.0, f"{main_value}/{bonus_part}", end_mark
        return 0.0, main_value.strip(), end_mark
    else:
        try:
            discount = float(main_value)
            return discount, bonus_part, end_mark
        except:
            return 0.0, value, end_mark

def generate_item_row(serial, item_name, value, preserve_end_marks=False):
    """Generate HTML for a single item row"""
    display_name = '          ' + item_name.upper().ljust(28)
    hidden_name = item_name.upper().ljust(50)
    discount, bonus, end_mark = parse_discount_value(value, preserve_end_marks)

    # Check if '/' was used in original value (bonus separator)
    has_slash_separator = '/' in value

    # Check if the original value contains "net" to handle "140 NET" type values specially
    original_value_lower = value.lower().strip()

    if 'net' in original_value_lower and any(c.isdigit() for c in value):
        # For values like "140 NET", display the original value in the discount column
        if has_slash_separator:
            # Extract main part before /
            main_part = value.split('/')[0].strip()
            discount_str = f'{main_part}'.rjust(len(main_part))
            bonus_str = bonus.ljust(44) if bonus else ' ' * 44
        else:
            discount_str = f'{value}'.rjust(len(value))
            bonus_str = ' ' * 44
    elif bonus and 'TP' in bonus.upper() and '/' in bonus:
        # Handle TP values with bonus separator like "TP,/something"
        tp_part, bonus_after = bonus.split('/', 1)
        discount_str = f'{tp_part}'.rjust(9)
        bonus_str = bonus_after.ljust(44) if bonus_after else ' ' * 44
    elif bonus and 'TP' in bonus.upper():
        # Handle TP values without separator (just "TP" or "TP,")
        discount_str = f'{bonus}'.rjust(9)
        bonus_str = ' ' * 44
    elif has_slash_separator and bonus:
        # '/' was used as separator - bonus goes in bonus column
        discount_str = f'{discount:.2f}%{end_mark}'.rjust(9 + len(end_mark))
        bonus_str = bonus.ljust(44)
    elif bonus:
        # No '/' separator but there's text after % - append to discount
        if discount > 0:
            discount_str = f'{discount:.2f}%{end_mark}{bonus}'.rjust(9 + len(end_mark) + len(bonus))
            bonus_str = ' ' * 44
        else:
            discount_str = f'0.00%{end_mark}{bonus}'.rjust(9 + len(end_mark) + len(bonus))
            bonus_str = ' ' * 44
    else:
        discount_str = f'{discount:.2f}%{end_mark}'.rjust(9 + len(end_mark))
        bonus_str = ' ' * 44

    return f'''<tr class="item"><td align="center">
 {str(serial).ljust(4)}
</td><td style=" text-align: left;" >
{display_name}
<input type="hidden" id="itnameid{serial}" value='{hidden_name}'>
</td><td align="center">
<input type="number" min="0" max="1000" class="qty" placeholder="Qty" id="nameid{serial}">
</td><td align="center">{discount_str}
</td><td colspan="3" align="center">
{bonus_str}
</td></tr>
'''

def generate_section_header(letter):
    return f'<tr><td colspan="7" align="center" style=" background: rgb(12,146,252); background: radial-gradient(circle, rgba(12,146,252,1) 50%, rgba(255,255,255,1) 100%); color:white;" ><b>{letter}</b></td></tr>'

def generate_js_vars_full(data_items, preserve_end_marks=False):
    """Generate JS variables for Printf and myfun (with ITMBONUS and ITMDISC)"""
    js_vars = ""
    for i, (item_name, value) in enumerate(data_items, 1):
        discount, bonus, end_mark = parse_discount_value(value, preserve_end_marks)
        has_slash = '/' in value

        # Special handling for "TP" and similar non-numeric values
        if 'TP' in value.upper():
            if has_slash and '/' in bonus:
                # TP with bonus separator like "TP,/5+5"
                tp_part, bonus_after = bonus.split('/', 1)
                discount_str = f'"{tp_part}"'
                bonus_str = f'"{bonus_after}"' if bonus_after else '""'
            else:
                # Plain TP or TP with comma
                discount_str = f'"{value}"'
                bonus_str = '""'
            js_vars += f'''
var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {discount_str};
var namevar{i}=document.getElementById("nameid{i}").value;
'''
        elif 'net' in value.lower():
            # For NET values like "330 NET", keep the original value
            if has_slash:
                main_part = value.split('/')[0].strip()
                discount_str = f'"{main_part}"'
                bonus_str = f'"{bonus}"' if bonus else '""'
            else:
                discount_str = f'"{value}"'
                bonus_str = '""'
            js_vars += f'''
var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {discount_str};
var namevar{i}=document.getElementById("nameid{i}").value;
'''
        else:
            # For numeric values — separate trailing suffix (,/.) from real bonus
            if _is_suffix_only(bonus):
                suffix_str = f'"{bonus.strip()}"'
                bonus_str  = '""'
            elif end_mark:
                suffix_str = f'"{end_mark}"'
                bonus_str  = f'"{bonus}"' if bonus else '""'
            else:
                suffix_str = '""'
                bonus_str  = f'"{bonus}"' if bonus else '""'
            js_vars += f'''
var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = "{discount:.2f}";
var ITMDISCSUFFIX{i} = {suffix_str};
var namevar{i}=document.getElementById("nameid{i}").value;
'''
    return js_vars

def generate_js_vars_createrows(data_items, preserve_end_marks=False):
    """Generate JS variables for createRows function (PDF generation)"""
    js_vars = ""
    for i, (item_name, value) in enumerate(data_items, 1):
        discount, bonus, end_mark = parse_discount_value(value, preserve_end_marks)
        has_slash = '/' in value

        # Special handling for "TP" and similar non-numeric values
        if 'TP' in value.upper():
            if has_slash and '/' in bonus:
                # TP with bonus separator like "TP,/5+5"
                tp_part, bonus_after = bonus.split('/', 1)
                discount_str = f'"{tp_part}"'
                bonus_str = f'"{bonus_after}"' if bonus_after else '""'
            else:
                discount_str = f'"{value}"'
                bonus_str = '""'
            js_vars += f'''var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {discount_str};
var namevar{i}=document.getElementById("nameid{i}").value;

var namevarr{i} = " ";
// Don't append % to non-numeric values like TP
'''
        elif 'net' in value.lower():
            # For NET values like "330 NET"
            if has_slash:
                main_part = value.split('/')[0].strip()
                discount_str = f'"{main_part}"'
                bonus_str = f'"{bonus}"' if bonus else '""'
            else:
                discount_str = f'"{value}"'
                bonus_str = '""'
            js_vars += f'''var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {discount_str};
var namevar{i}=document.getElementById("nameid{i}").value;

var namevarr{i} = " ";
// Don't append % to NET values
'''
        else:
            # For numeric values — suffix (,/.) goes into ITMDISC, real bonus into ITMBONUS
            if _is_suffix_only(bonus):
                disc_display = f'"{discount:.2f}%{bonus.strip()}"'
                bonus_str    = '""'
            elif end_mark:
                disc_display = f'"{discount:.2f}%{end_mark}"'
                bonus_str    = f'"{bonus}"' if bonus else '""'
            else:
                disc_display = f'"{discount:.2f}%"'
                bonus_str    = f'"{bonus}"' if bonus else '""'
            js_vars += f'''var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {disc_display};
var namevar{i}=document.getElementById("nameid{i}").value;

var namevarr{i} = " ";
'''
    return js_vars

def generate_js_vars_simple(data_items, preserve_end_marks=False):
    """Generate JS variables for mywht (including ITMCODE, ITMNAME, ITMBONUS, ITMDISC, namevar)"""
    js_vars = ""
    for i, (item_name, value) in enumerate(data_items, 1):
        discount, bonus, end_mark = parse_discount_value(value, preserve_end_marks)
        has_slash = '/' in value

        # Special handling for "TP" and similar non-numeric values
        if 'TP' in value.upper():
            if has_slash and '/' in bonus:
                # TP with bonus separator like "TP,/5+5"
                tp_part, bonus_after = bonus.split('/', 1)
                discount_str = f'"{tp_part}"'
                bonus_str = f'"{bonus_after}"' if bonus_after else '""'
            else:
                discount_str = f'"{value}"'
                bonus_str = '""'
            js_vars += f'''
var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} = {discount_str};
var namevar{i}=document.getElementById("nameid{i}").value;
'''
        else:
            if _is_suffix_only(bonus):
                suffix_str = f'"{bonus.strip()}"'
                bonus_str  = '""'
            elif end_mark:
                suffix_str = f'"{end_mark}"'
                bonus_str  = f'"{bonus}"' if bonus else '""'
            else:
                suffix_str = '""'
                bonus_str  = f'"{bonus}"' if bonus else '""'
            js_vars += f'''
var ITMCODE{i} = "{i}";
var ITMNAME{i} =document.getElementById("itnameid{i}").value;
var ITMBONUS{i} = {bonus_str};
var ITMDISC{i} =       {discount:8.2f}    ;
var ITMDISCSUFFIX{i} = {suffix_str};
var namevar{i}=document.getElementById("nameid{i}").value;
'''
    return js_vars

def generate_js_if_blocks(data_items, window_var='mywindow'):
    """Generate JS if blocks for Printf and myfun"""
    js_blocks = ""
    for i in range(1, len(data_items) + 1):
        item_value = data_items[i-1][1]  # Get the original value
        is_special = 'TP' in item_value.upper() or 'net' in item_value.lower()

        if is_special:
            # For TP and NET values, don't append %
            js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{

var serial = (serial+1);
 {window_var}.document.write('<tr class="item"><td align="center">');
 {window_var}.document.write(ITMCODE{i});
 {window_var}.document.write('</td><td style="text-align:left;">');
 {window_var}.document.write(ITMNAME{i});
 {window_var}.document.write('</td><td align="right">');
 {window_var}.document.write(namevar{i});
 {window_var}.document.write('</td><td align="right">');
 {window_var}.document.write(ITMDISC{i});
 {window_var}.document.write('</td><td align="center">');
 {window_var}.document.write(ITMBONUS{i});
 {window_var}.document.write('</td></tr>');
}}
'''
        else:
            # For regular percentage values, append %
            js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{

var serial = (serial+1);
 {window_var}.document.write('<tr class="item"><td align="center">');
 {window_var}.document.write(ITMCODE{i});
 {window_var}.document.write('</td><td style="text-align:left;">');
 {window_var}.document.write(ITMNAME{i});
 {window_var}.document.write('</td><td align="right">');
 {window_var}.document.write(namevar{i});
 {window_var}.document.write('</td><td align="right">');
 {window_var}.document.write(ITMDISC{i});
 {window_var}.document.write(' %' + (typeof ITMDISCSUFFIX{i} !== "undefined" ? ITMDISCSUFFIX{i} : "") + '</td><td align="center">');
 {window_var}.document.write(ITMBONUS{i});
 {window_var}.document.write('</td></tr>');
}}
'''
    return js_blocks

def generate_js_if_blocks_pdf(data_items):
    """Generate JS if blocks for myfun PDF (rows.push)"""
    js_blocks = ""
    for i in range(1, len(data_items) + 1):
        js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{

var serial = (serial+1);
rows.push([ITMCODE{i}, ITMNAME{i}, namevar{i}, ITMDISC{i}]);
}}
'''
    return js_blocks

def generate_js_if_blocks_whatsapp(data_items):
    """Generate JS if blocks for mywht (WhatsApp)"""
    js_blocks = ""

    for i in range(1, len(data_items) + 1):
        # Check if this is a special case like "TP" that shouldn't get % appended
        item_value = data_items[i-1][1]  # Get the original value
        is_special_value = item_value.upper() == 'TP' or 'TP' in item_value.upper()

        if i <= 3:  # Add header check to first few items to ensure it gets added
            # For the first few items, add header if it hasn't been added yet
            if is_special_value:
                # For special values like TP, don't add % to discText
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
// Add header once at the beginning if it hasn't been added yet
if(text == "") {{
 text = "*Name* :%0a*List no* :000085(1)%0a--------------------%0a|%20*Code*%20|%20*QTY*%20|%20*ITM*%20|%20*DISC*%20|%20*Bonus*%20|%0a--------------------%0a";
}}
var serial = (serial+1);

 // For special values like TP, don't append %
 var discText = ITMDISC{i};
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMBONUS{i};
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a";
}}
'''
            else:
                # For numeric values, use original logic
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
// Add header once at the beginning if it hasn't been added yet
if(text == "") {{
 text = "*Name* :%0a*List no* :000085(1)%0a--------------------%0a|%20*Code*%20|%20*QTY*%20|%20*ITM*%20|%20*DISC*%20|%20*Bonus*%20|%0a--------------------%0a";
}}
var serial = (serial+1);

 // Show discount with % if non-zero, otherwise show empty in discount column
 var discText = ITMDISC{i} != 0 ? ITMDISC{i} + "%" + (typeof ITMDISCSUFFIX{i} !== "undefined" ? ITMDISCSUFFIX{i} : "") : "";
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMDISC{i} == 0 ? ITMBONUS{i} : "";
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a";
}}
'''
        elif i == len(data_items):
            # For the last item, add the item and total
            if is_special_value:
                # For special values like TP, don't add % to discText
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
var serial = (serial+1);

 // For special values like TP, don't append %
 var discText = ITMDISC{i};
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMBONUS{i};
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a"+"%0a*Total* *Items* : "+serial;
}}
'''
            else:
                # For numeric values, use original logic
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
var serial = (serial+1);

 // Show discount with % if non-zero, otherwise show empty in discount column
 var discText = ITMDISC{i} != 0 ? ITMDISC{i} + "%" + (typeof ITMDISCSUFFIX{i} !== "undefined" ? ITMDISCSUFFIX{i} : "") : "";
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMDISC{i} == 0 ? ITMBONUS{i} : "";
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a"+"%0a*Total* *Items* : "+serial;
}}
'''
        else:
            # For other items, just add the item
            if is_special_value:
                # For special values like TP, don't add % to discText
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
var serial = (serial+1);

 // For special values like TP, don't append %
 var discText = ITMDISC{i};
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMBONUS{i};
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a";
}}
'''
            else:
                # For numeric values, use original logic
                js_blocks += f'''if(namevar{i}==0 ){{
}}
else {{
var serial = (serial+1);

 // Show discount with % if non-zero, otherwise show empty in discount column
 var discText = ITMDISC{i} != 0 ? ITMDISC{i} + "%" + (typeof ITMDISCSUFFIX{i} !== "undefined" ? ITMDISCSUFFIX{i} : "") : "";
 // Show bonus in bonus column if discount is 0, otherwise show empty
 var bonusText = ITMDISC{i} == 0 ? ITMBONUS{i} : "";
 var text=text+"|"+ITMCODE{i}+"%20|%20"+namevar{i}+"%20|%20"+ITMNAME{i}+"%20|%20"+discText+"%20|%20"+bonusText+"%20|%0a--------------------%0a";
}}
'''
    return js_blocks

def _parse_disc_to_num(value):
    """Pull a numeric percent out of a string like '7.00%' or '7%' or '7'. Returns 0.0 if none."""
    if not value:
        return 0.0
    cleaned = value.strip()
    # NET and TP values are rates, not discount percentages → 0%
    if 'net' in cleaned.lower() or cleaned.upper().startswith('TP'):
        return 0.0
    if '%' in cleaned:
        cleaned = cleaned.split('%')[0].strip()
    # Drop everything after first non-numeric
    out = ""
    for ch in cleaned:
        if ch.isdigit() or ch == '.':
            out += ch
        else:
            break
    try:
        return float(out) if out else 0.0
    except ValueError:
        return 0.0

def _new_format_item_row(serial, code, name, disc_num, bonus, tp, tax, list_no="", disc_raw=""):
    """Render one <tr class="item-row"> for the new format."""
    code_disp = (code or str(serial)).strip()
    data_id = f"{code_disp}-{list_no}-{serial}"
    disc_str = f"{disc_num:.2f}"
    # Show the original value string (e.g. "14.00%,") if available, else fall back to formatted number
    disc_disp = disc_raw.strip() if disc_raw and disc_raw.strip() else f"{disc_str}%"
    # Extract trailing suffix after % (e.g. "," or ".") to preserve in WhatsApp/PDF
    _suffix_m = re.search(r'%(.+)$', disc_raw.strip()) if disc_raw else None
    disc_suffix = _suffix_m.group(1).strip() if _suffix_m else ""
    def _safe_num(val):
        if not val:
            return "0.00"
        cleaned = ''.join(ch for ch in str(val) if ch.isdigit() or ch == '.')
        try:
            return f"{float(cleaned):.2f}" if cleaned else "0.00"
        except ValueError:
            return "0.00"
    tp_str = _safe_num(tp)
    tax_str = _safe_num(tax)
    bonus_attr = (bonus or "").strip()
    name_disp = name.strip()

    return (
        f'<tr class="item-row" data-id="{data_id}" data-code="{code_disp}" data-name="{name_disp}" '
        f'data-tp="{tp_str}" data-disc="{disc_str}" data-disc-suffix="{disc_suffix}" '
        f'data-bonus="{bonus_attr}" data-tax="{tax_str}">'
        f'<td class="first-col"> {code_disp} </td>'
        f'<td class="cell-name">{name_disp}</td>'
        f'<td><div class="qty-wrap"><input class="qty-input" type="number" min="0" max="5000" '
        f'step="1" placeholder="0" inputmode="numeric"></div></td>'
        f'<td class="num">{disc_disp}</td>'
        f'<td>{bonus_attr}</td>'
        f'<td class="num">{tp_str}</td>'
        f'<td align="center">{tax_str}</td>'
        f'</tr>\n'
    )

def _new_format_letter_header(letter):
    """Section header row for the new format (alphabet letter, styled like company-head)."""
    return f'<tr class="company-head"><td colspan="7">{letter}</td></tr>\n'

def generate_html_new_format(template_path, items_extended, list_no="000001",
                             list_date=None, title="ANAS SYSTEM", whatsapp_number="923337068868",
                             message=""):
    """Generate a new-format HTML offer list.

    items_extended: list of dicts with keys name, value, code, tp, bonus, tax.
    Sorts alphabetically by name and emits A/B/C section headers (per user request:
    "company doesn't matter, alphabetic order").
    """
    import datetime
    if list_date is None:
        list_date = datetime.datetime.now().strftime("%d/%m/%Y")

    with open(template_path, 'r', encoding='utf-8', newline='') as f:
        content = f.read()

    # Sort by uppercase name for stable alphabetic grouping.
    sorted_items = sorted(items_extended, key=lambda d: (d.get('name') or "").upper())

    items_html = ""
    current_letter = ""
    for i, it in enumerate(sorted_items, 1):
        name = it.get('name') or ""
        first_letter = name[0].upper() if name else "?"
        if first_letter != current_letter:
            current_letter = first_letter
            items_html += _new_format_letter_header(current_letter)
        disc_raw = it.get('value') or ""
        disc_num = _parse_disc_to_num(disc_raw)
        items_html += _new_format_item_row(
            serial=i,
            code=str(i),
            name=name,
            disc_num=disc_num,
            disc_raw=disc_raw,
            bonus=it.get('bonus') or "",
            tp=it.get('tp') or "",
            tax=it.get('tax') or "0.00",
            list_no=list_no,
        )

    # Insert items into the placeholder.
    if "<!--ITEMS_PLACEHOLDER-->" in content:
        content = content.replace("<!--ITEMS_PLACEHOLDER-->", items_html, 1)
    else:
        return None, "ERROR: Template missing <!--ITEMS_PLACEHOLDER-->"

    # Replace the sample list-no in all three places. The header meta has stray
    # CR characters between fields, so use regex with [\s] tolerant matching.
    # 1) Header: "<b>List No : </b>{listno}<b>Date :{date}</div>"
    content = re.sub(
        r'(<b>List No : </b>)\s*000032\s*(<b>Date :)\s*12/04/2026',
        lambda m: f'{m.group(1)}{list_no}{m.group(2)}{list_date}',
        content,
    )
    # 2) JS OFFLINE_META.offerId
    content = content.replace('offerId: "000032"', f'offerId: "{list_no}"')
    # 3) buildWaMessage hard-coded "*List No* : 000032\n"
    content = content.replace('*List No* : 000032\\n', f'*List No* : {list_no}\\n')

    # Browser tab title
    content = content.replace(
        'ANAS SYSTEM  Offline Offer List',
        f'{title} Offer List' if title.strip() else 'Offline Offer List'
    )

    # Shop title — OFFLINE_META.shopTitle JS value
    content = re.sub(r'shopTitle:\s*"[^"]*"', f'shopTitle: "{title}"', content)

    # Shop title — <h1 class="shopname"> HTML element
    content = re.sub(r'(<h1[^>]*class="shopname"[^>]*>)[^<]*(</h1>)',
                     lambda m: m.group(1) + title + m.group(2), content)

    # Footer company name
    content = re.sub(r'<strong>[^<]*MEDICO[^<]*</strong>', f'<strong>{title}</strong>' if title.strip() else '', content)

    # Custom message below offer list title
    msg = message.strip() if message else ''
    if msg:
        msg_html = f'<div style="text-align:center;padding:6px 16px;font-size:14px;color:#555;font-style:italic;">{msg}</div>'
    else:
        msg_html = ''
    content = content.replace('<!--MESSAGE_PLACEHOLDER-->', msg_html)

    # Message in OFFLINE_META for JS (preview & PDF)
    content = content.replace('__MSG_PLACEHOLDER__', msg.replace('"', '&quot;').replace("'", "\\'"))

    # Qty expiry — fixed 10 hours
    content = content.replace('__QTY_EXPIRE__', '10')

    # WhatsApp number — both the hidden input and the JS fallback use the same string.
    content = content.replace('+03112127664 ', whatsapp_number)

    return content, None

def update_htm(htm_filepath, data_items, output_filepath):
    """Update list.HTM with all items from data.txt"""
    with open(htm_filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    total_count = len(data_items)

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
        print("ERROR: Could not find tbody section")
        return

    items_html = ""
    current_letter = ""
    for i, (item_name, value) in enumerate(data_items, 1):
        first_letter = item_name[0].upper() if item_name else "?"
        if first_letter != current_letter:
            current_letter = first_letter
            items_html += generate_section_header(current_letter)
        items_html += generate_item_row(i, item_name, value)

    items_html += f'''<tr class="heading2"> <td style=" text-align: CENTER; border-radius: 0px 0px 16px 16px; padding-left: 10px;" colspan="5" >Total Products :
  {total_count}
</td></tr>
'''

    content = content[:tbody_start + len('<tbody id="myTable">')] + items_html + content[tbody_end:]

    # 3. Generate new JS content
    js_vars_full = generate_js_vars_full(data_items)
    js_vars_simple = generate_js_vars_simple(data_items)
    js_if_blocks_printf = generate_js_if_blocks(data_items, 'mywindow')
    js_if_blocks_myfun = generate_js_if_blocks(data_items, 'myWindow')
    js_if_whatsapp = generate_js_if_blocks_whatsapp(data_items)

    # 4. Update Printf function
    # Variables: from "var serial = 0;" to "var mywindow = window.open"
    content = re.sub(
        r'(function Printf\(\)\{\nvar ITDATE = "[^"]*";\nvar LSTNO = "[^"]*";\nvar custname = document\.getElementById\("cstname"\)\.value;\nvar serial = 0;\n)'
        r'.*?'
        r'(\n\n\n var mywindow = window\.open)',
        r'\1' + js_vars_full + r'\2',
        content,
        flags=re.DOTALL
    )

    # Printf if blocks: from "if(namevar1==0" to before "mywindow.document.write('<tr class=\"heading2\">"
    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\n mywindow\.document\.write\('<tr class=\"item\">.*?"
        r"( mywindow\.document\.write\('<tr class=\"heading2\"> <td)",
        js_if_blocks_printf + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    # 5. Update mywht function
    # Variables: from "var serial = 0;" to before "if(namevar1==0"
    content = re.sub(
        r'(function mywht\(\)\{\nvar ITDATE = "[^"]*";\nvar LSTNO = "[^"]*";\nvar custname = document\.getElementById\("cstname"\)\.value;\nvar text= "";\n\nvar serial = 0;\n)'
        r'.*?'
        r'(if\(namevar1==0 \))',
        r'\1' + js_vars_simple + r'\n\2',
        content,
        flags=re.DOTALL
    )

    # mywht if blocks: from first if to before "var url="
    content = re.sub(
        r'(function mywht\(\)\{.*?var serial = 0;\n)'
        r'.*?'
        r'(\nvar url="https://wa\.me)',
        r'\1' + js_vars_simple + '\n' + js_if_whatsapp + r'\2',
        content,
        flags=re.DOTALL
    )

    # 6. Update myfun function
    # Variables: from "var serial = 0;" to "myWindow=window.open"
    content = re.sub(
        r'(function myfun\(\)\{\nvar ITDATE = "[^"]*";\nvar LSTNO = "[^"]*";\nvar custname = document\.getElementById\("cstname"\)\.value;\nvar serial = 0;\n)'
        r'.*?'
        r'(\nmyWindow=window\.open)',
        r'\1' + js_vars_full + r'\2',
        content,
        flags=re.DOTALL
    )

    # myfun if blocks (preview): from "if(namevar1==0" to before "myWindow.document.write('<tr class=\"heading2\">"
    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\n myWindow\.document\.write\('<tr class=\"item\">.*?"
        r"( myWindow\.document\.write\('<tr class=\"heading2\"> <td)",
        js_if_blocks_myfun + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    # 7. Update createRows function (PDF generation)
    js_vars_createrows = generate_js_vars_createrows(data_items)
    js_if_blocks_pdf = generate_js_if_blocks_pdf(data_items)

    # Update createRows variables: from "const rows = [];" to "var serial = 0;"
    content = re.sub(
        r'(function createRows\(count\) \{\n  const rows = \[\];\n\n)'
        r'.*?'
        r'(var serial = 0;)',
        r'\1' + js_vars_createrows + r'\2',
        content,
        flags=re.DOTALL
    )

    # Update createRows if blocks (PDF): rows.push blocks
    content = re.sub(
        r"if\(namevar1==0 \)\{\n\}\nelse \{\n\nvar serial = \(serial\+1\);\nrows\.push.*?"
        r"(\nvar totitem=)",
        js_if_blocks_pdf + r'\1',
        content,
        flags=re.DOTALL,
        count=1
    )

    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Generated {total_count} items in table")
    print(f"Updated Printf, mywht, myfun, createRows functions")
    print(f"Total Products: {total_count}")

if __name__ == '__main__':
    data_file = 'data.txt'
    htm_file = 'list.HTM'

    print("Reading data.txt...")
    data_items = parse_data_txt(data_file)
    print(f"Found {len(data_items)} items in data.txt")

    print("\nUpdating list.HTM...")
    update_htm(htm_file, data_items, htm_file)

    print("\nDone!")
