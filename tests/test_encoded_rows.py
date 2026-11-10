import base64
import json
import unittest

from bs4 import BeautifulSoup
from encoded_rows import decode_item_rows


def wrapped_html(rows, modern=False):
    seed = 987316526 if modern else 23
    previous = seed & 255
    key = list(range(32)) if modern else [12, 98, 145]
    stride = ((seed >> 8) & 255) | 1 if modern else 31
    offset = (seed >> 16) & 31 if modern else 0
    encoded = bytearray()
    digest = 2166136261
    for index, plain in enumerate(rows.encode()):
        value = plain ^ ((key[(index + offset) % len(key)] + (index % 256) * stride + previous) & 255)
        encoded.append(value)
        previous = value
        digest = ((digest ^ plain) * 16777619) & 0xffffffff
    text = base64.b64encode(encoded).decode()
    if modern:
        chunks = [text[8:16], text[16:], text[:8]]
        return ('<tbody id="itemsBody"></tbody><script>'
                'var target=document.getElementById("itemsBody");'
                f'const _abc_chunks={json.dumps(chunks)},_abc_map=[1,2,0],'
                f'_abc_key={json.dumps(key)},_abc_seed={seed},_abc_order=[];'
                f"if(_abc_hash!=={digest})throw new Error('Invalid offer data');</script>")
    data = json.dumps([text])
    return ('<tbody id="itemsBody"></tbody><script>'
            'var target=document.getElementById("itemsBody");'
            f'var a={data},b=[0],c={json.dumps(key)},d=23,t="";'
            f'if(f!=={digest})throw 0;</script>')


class EncodedRowsTest(unittest.TestCase):
    def test_modern_shuffled_chunks_and_seed(self):
        rows = '<tr class="item-row" data-tp="535.50"><td>Crème &amp; Co</td></tr>'
        soup = BeautifulSoup(wrapped_html(rows, modern=True), 'html.parser')
        decode_item_rows(soup)
        self.assertEqual(soup.select_one('tbody tr')['data-tp'], '535.50')
        self.assertEqual(soup.select_one('tbody td').text, 'Crème & Co')

    def test_modern_invalid_map_and_checksum(self):
        html = wrapped_html('<tr><td>Item</td></tr>', modern=True)
        for damaged in (html.replace('[1,2,0]', '[1,1,0]'),
                        html.replace('if(_abc_hash!==', 'if(_abc_hash!==9')):
            with self.subTest(damaged=damaged):
                with self.assertRaises(ValueError):
                    decode_item_rows(BeautifulSoup(damaged, 'html.parser'))

    def test_recovers_unicode_and_attributes_without_running_script(self):
        rows = '<tr class="item-row" data-disc="6.00"><td>Crème &amp; Co</td></tr>'
        soup = BeautifulSoup(wrapped_html(rows), 'html.parser')
        decode_item_rows(soup)
        self.assertEqual(soup.select_one('tbody tr')['data-disc'], '6.00')
        self.assertEqual(soup.select_one('tbody td').text, 'Crème & Co')
        decode_item_rows(soup)
        self.assertEqual(len(soup.select('tbody tr')), 1)

    def test_rejects_corrupt_data(self):
        html = wrapped_html('<tr><td>Item</td></tr>')
        soup = BeautifulSoup(html.replace('if(f!==', 'if(f!==9'), 'html.parser')
        with self.assertRaises(ValueError):
            decode_item_rows(soup)

    def test_ordinary_empty_table_is_unchanged(self):
        soup = BeautifulSoup('<tbody id="itemsBody"></tbody>', 'html.parser')
        decode_item_rows(soup)
        self.assertIsNone(soup.find('tr'))


if __name__ == '__main__':
    unittest.main()
