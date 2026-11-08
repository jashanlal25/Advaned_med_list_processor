import base64
import json
import unittest

from bs4 import BeautifulSoup
from encoded_rows import decode_item_rows


def wrapped_html(rows):
    previous = 23
    key = [12, 98, 145]
    encoded = bytearray()
    digest = 2166136261
    for index, plain in enumerate(rows.encode()):
        value = plain ^ ((key[index % len(key)] + (index % 256) * 31 + previous) & 255)
        encoded.append(value)
        previous = value
        digest = ((digest ^ plain) * 16777619) & 0xffffffff
    data = json.dumps([base64.b64encode(encoded).decode()])
    return ('<tbody id="itemsBody"></tbody><script>'
            'var target=document.getElementById("itemsBody");'
            f'var a={data},b=[0],c={json.dumps(key)},d=23,t="";'
            f'if(f!=={digest})throw 0;</script>')


class EncodedRowsTest(unittest.TestCase):
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
