"""Read ANAS offline item data without executing uploaded JavaScript."""
import base64
import json
import re


def decode_item_rows(soup):
    """Fill an empty itemsBody from the supported, checksummed data wrapper."""
    target = soup.find('tbody', id='itemsBody')
    if target is None or target.find('tr') is not None:
        return
    for script in soup.find_all('script'):
        source = script.string or ''
        if not re.search(r'var target=document\.getElementById\([\"\']itemsBody[\"\']\)', source):
            continue
        match = re.search(
            r'var a=(\[.*?\]),b=(\[.*?\]),c=(\[.*?\]),d=(\d+),t=', source, re.S)
        checksum = re.search(r'if\(f!==(\d+)\)throw 0', source)
        modern = re.search(r'const ([_a-zA-Z0-9]+)_chunks=', source)
        stride, offset = 31, 0
        if modern:
            prefix = re.escape(modern[1])
            match = re.search(
                prefix + r'_chunks=(\[.*?\]),' + prefix + r'_map=(\[.*?\]),'
                + prefix + r'_key=(\[.*?\]),' + prefix + r'_seed=(\d+),', source, re.S)
            checksum = re.search(r'if\(' + prefix + r'_hash!==(\d+)\)', source)
        if not match or not checksum:
            raise ValueError('Unsupported encoded item data in this HTM file.')
        try:
            chunks, order, key = map(json.loads, match.group(1, 2, 3))
            if (not isinstance(chunks, list) or not all(isinstance(x, str) for x in chunks)
                    or not isinstance(order, list) or not isinstance(key, list) or not key
                    or not all(type(x) is int and 0 <= x < len(chunks) for x in order)
                    or not all(type(x) is int and 0 <= x <= 255 for x in key)):
                raise ValueError('Invalid encoded item data')
            if modern:
                if len(key) != 32 or sorted(order) != list(range(len(chunks))):
                    raise ValueError('Invalid encoded item map')
                arranged = [''] * len(chunks)
                for chunk, position in zip(chunks, order):
                    arranged[position] = chunk
                chunks, order = arranged, list(range(len(arranged)))
                seed = int(match[4])
                stride, offset = ((seed >> 8) & 255) | 1, (seed >> 16) & 31
            encoded = base64.b64decode(''.join(chunks[i] for i in order), validate=True)
            previous = int(match[4]) & 255
            decoded = bytearray()
            digest = 2166136261
            for index, value in enumerate(encoded):
                plain = value ^ ((key[(index + offset) % len(key)] + (index % 256) * stride + previous) & 255)
                decoded.append(plain)
                previous = value
                digest = ((digest ^ plain) * 16777619) & 0xffffffff
            if digest != int(checksum[1]):
                raise ValueError('Item data checksum mismatch')
            from bs4 import BeautifulSoup
            fragment = BeautifulSoup(decoded.decode('utf-8'), 'html.parser')
            for row in list(fragment.find_all('tr', recursive=False)):
                target.append(row)
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise ValueError('Cannot read encoded items: the HTM data is damaged or unsupported.') from exc
        return
