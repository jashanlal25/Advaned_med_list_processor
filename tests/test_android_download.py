import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from flask import Flask
from android_download import android_download, APK_URL


class AndroidDownloadTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(android_download)
        self.client = self.app.test_client()  # No login or cookies.

    def upstream(self, data, length=None):
        response = io.BytesIO(data)
        response.status = 200
        response.headers = {'Content-Length': str(len(data) if length is None else length)}
        return response

    def test_public_attachment_has_no_redirect_or_upstream_headers(self):
        apk = b'PK\x03\x04test-apk-bytes'
        with patch('android_download.urlopen', return_value=self.upstream(apk)) as fetch:
            response = self.client.get('/download/android?url=https://example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, apk)
        self.assertEqual(response.mimetype, 'application/vnd.android.package-archive')
        self.assertIn('attachment; filename=MedList-Native.apk', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn('Location', response.headers)
        self.assertNotIn('Set-Cookie', response.headers)
        self.assertEqual(fetch.call_args.args[0].full_url, APK_URL)

    def test_errors_do_not_expose_github(self):
        for error in (HTTPError(APK_URL, 404, 'missing', {}, None), URLError('timeout')):
            with self.subTest(error=type(error).__name__), patch('android_download.urlopen', side_effect=error):
                response = self.client.get('/download/android')
                self.assertEqual(response.status_code, 502)
                self.assertNotIn(b'github', response.data)
                self.assertNotIn('Location', response.headers)

    def test_html_and_truncated_responses_are_not_downloaded_as_apks(self):
        for data, length in ((b'<html>Error</html>', 18), (b'PK\x03\x04short', 200)):
            with self.subTest(data=data), patch('android_download.urlopen', return_value=self.upstream(data, length)):
                self.assertEqual(self.client.get('/download/android').status_code, 502)

    def test_head_is_public_and_has_no_body(self):
        with patch('android_download.urlopen', return_value=self.upstream(b'PK\x03\x04apk')):
            response = self.client.head('/download/android')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'')
        self.assertEqual(response.content_length, 7)


if __name__ == '__main__':
    unittest.main()
