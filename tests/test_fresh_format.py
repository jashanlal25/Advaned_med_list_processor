"""Fresh presentation must preserve the established offer-list data and engine."""
import io
import unittest
from bs4 import BeautifulSoup
from app import app


class FreshFormatTests(unittest.TestCase):
    def generate(self, kind):
        response = app.test_client().post('/generate-html', data={
            'file': (io.BytesIO(b'Alpha----- 10%,|100|2+1|1\nBeta----- 50 NET|200||0'), 'test.txt'),
            'output_format': kind, 'title': 'TEST PHARMA', 'list_no': '42',
            'whatsapp_number': '923001234567', 'message': 'Test offer',
        })
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_fresh_preserves_new_format_fields_and_scripts(self):
        fresh_result = self.generate('fresh')
        new_result = self.generate('new')
        fresh = BeautifulSoup(fresh_result['fresh_file']['data'], 'html.parser')
        new = BeautifulSoup(new_result['new_file']['data'], 'html.parser')
        self.assertEqual(str(fresh.select_one('#itemsBody')), str(new.select_one('#itemsBody')))
        # Payload and WhatsApp builder remain the same; Fresh embeds its UI runtime.
        self.assertEqual(str(fresh.find('script')), str(new.find('script')))
        self.assertFalse(fresh.select('script[src]'))
        self.assertEqual(len(fresh.select('.offline-blessing')), 1)
        self.assertNotIn('https://anas-system.com/bis.png', str(fresh))
        self.assertIn('Open in Edge Browser on iPhone and Chrome Browser on Android', fresh.get_text())
        self.assertEqual(fresh.select_one('#pdfForm')['action'], 'http://localhost/order/pdf')
        self.assertEqual(fresh.select_one('#shopTitle').text, 'TEST PHARMA')
        self.assertEqual(fresh.select_one('#waNumber')['value'], '923001234567')
        self.assertEqual(fresh_result['filename'], 'TEST_M42_fresh.htm')
        self.assertEqual(fresh.html['data-glass-depth'], '3d')
        self.assertFalse(fresh.select('#showcaseOnlineLinkBox,.anas-system-brandline'))
        self.assertNotIn('ANAS SYSTEM (SHUMAIL)', fresh.get_text())
        self.assertNotIn('data-glass-depth', new.html.attrs)

    def test_pdf_export_from_fresh_payload(self):
        response = app.test_client().post('/order/pdf', data={
            'payload': '{"offerId":"42","shopTitle":"TEST","customerName":"Buyer","items":[{"name":"Alpha","qty":2,"tp":100,"disc":10,"discSuffix":",","bonus":"2+1","tax":1,"lineNet":182}],"netTotal":182}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'%PDF-'))

    def test_both_still_generates_only_old_and_new(self):
        result = self.generate('both')
        self.assertIn('old_file', result)
        self.assertIn('new_file', result)
        self.assertNotIn('fresh_file', result)


if __name__ == '__main__':
    unittest.main()
