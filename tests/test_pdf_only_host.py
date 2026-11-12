"""The neutral hostname must expose PDFs without exposing the application UI."""
import io
import json
import unittest
from bs4 import BeautifulSoup
from app import app, PDF_PUBLIC_ORIGIN


class PdfOnlyHostTests(unittest.TestCase):
    def test_neutral_host_blocks_app_routes_without_redirect(self):
        client = app.test_client()
        for path in ('/', '/make_html', '/search', '/deduplicate', '/diff',
                     '/static/shared-store.js', '/manifest.json', '/order/pdf'):
            with self.subTest(path=path):
                response = client.get(path, base_url=PDF_PUBLIC_ORIGIN)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.get_data(as_text=True), 'Not Found')
                self.assertNotIn('Location', response.headers)
        response = client.post('/generate-html', base_url=PDF_PUBLIC_ORIGIN)
        self.assertEqual(response.status_code, 404)

    def test_pdf_page_and_open_work_on_neutral_host(self):
        client = app.test_client()
        payload = json.dumps({'shopTitle': 'Test Business', 'offerId': '42',
                              'items': [{'name': 'Alpha', 'qty': 1, 'tp': 100}],
                              'netTotal': 100})
        response = client.post('/order/pdf', base_url=PDF_PUBLIC_ORIGIN,
                               data={'payload': payload}, headers={'Accept': 'text/html'})
        self.assertEqual(response.status_code, 200)
        page = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(page.h1.text, 'Test Business — PDF Order')
        for action in ('open', 'download'):
            form = page.select_one(f'input[value="{action}"]').find_parent('form')
            fields = {field['name']: field['value'] for field in form.select('input')}
            response = client.post(form['action'], base_url=PDF_PUBLIC_ORIGIN,
                                   data=fields, headers={'Accept': 'text/html'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(b'%PDF-'))

    def test_normal_host_keeps_app_and_generates_neutral_pdf_target(self):
        client = app.test_client()
        for path in ('/', '/make_html'):
            self.assertEqual(client.get(path).status_code, 200)
        response = client.post('/generate-html', data={
            'file': (io.BytesIO(b'Alpha----- 10%|100||0'), 'test.txt'),
            'output_format': 'fresh', 'title': 'Test Business',
        })
        self.assertEqual(response.status_code, 200)
        page = BeautifulSoup(response.get_json()['fresh_file']['data'], 'html.parser')
        self.assertEqual(page.select_one('#pdfForm')['action'], PDF_PUBLIC_ORIGIN + '/order/pdf')


if __name__ == '__main__':
    unittest.main()
