"""Mobile PDF actions must work without blob URLs or instance-local state."""
import json
import unittest
from bs4 import BeautifulSoup
from app import app


class OrderPdfActionTests(unittest.TestCase):
    def test_share_page_open_and_download_round_trip(self):
        payload = {'offerId': '42', 'shopTitle': 'Test & Co',
                   'customerName': 'Buyer "A" <test>', 'netTotal': 182,
                   'items': [{'code': 'A837', 'name': 'Alpha', 'qty': 2,
                              'tp': 100, 'disc': 10, 'discSuffix': ',',
                              'bonus': '2+1', 'tax': 1, 'lineNet': 182}]}
        client = app.test_client()
        page = client.post('/order/pdf', data={'payload': json.dumps(payload)},
                           headers={'Accept': 'text/html'})
        self.assertEqual(page.status_code, 200)
        soup = BeautifulSoup(page.data, 'html.parser')
        self.assertIsNotNone(soup.select_one('#openPdf'))
        self.assertEqual(soup.h1.text, 'Test & Co — PDF Order')
        self.assertEqual(soup.title.text, 'Test & Co — PDF Order')
        self.assertNotIn('MedList PDF Order', page.get_data(as_text=True))
        for action in ('open', 'download'):
            control = soup.select_one(f'input[name="pdf_action"][value="{action}"]')
            form = control.find_parent('form')
            fields = {field['name']: field['value'] for field in form.select('input')}
            self.assertEqual(json.loads(fields['payload']), payload)
            # A fresh client simulates another Vercel instance, without cookies.
            response = app.test_client().post(form['action'], data=fields,
                                              headers={'Accept': 'text/html'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'application/pdf')
            self.assertTrue(response.data.startswith(b'%PDF-'))
            disposition = 'inline' if action == 'open' else 'attachment'
            self.assertTrue(response.headers['Content-Disposition'].startswith(disposition))
            self.assertEqual(response.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
