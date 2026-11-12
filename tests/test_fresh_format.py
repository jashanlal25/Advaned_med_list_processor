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
        self.assertEqual([str(s) for s in fresh.find_all('script')],
                         [str(s) for s in new.find_all('script')])
        self.assertEqual(fresh.select_one('#shopTitle').text, 'TEST PHARMA')
        self.assertEqual(fresh.select_one('#waNumber')['value'], '923001234567')
        self.assertEqual(fresh_result['filename'], 'TEST_M42_fresh.htm')
        self.assertEqual(fresh.html['data-glass-depth'], '3d')
        self.assertFalse(fresh.select('#showcaseOnlineLinkBox,.anas-system-brandline'))
        self.assertNotIn('ANAS SYSTEM (SHUMAIL)', fresh.get_text())
        self.assertNotIn('data-glass-depth', new.html.attrs)

    def test_both_still_generates_only_old_and_new(self):
        result = self.generate('both')
        self.assertIn('old_file', result)
        self.assertIn('new_file', result)
        self.assertNotIn('fresh_file', result)


if __name__ == '__main__':
    unittest.main()
