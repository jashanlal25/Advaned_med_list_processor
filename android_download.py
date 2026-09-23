"""Public, same-origin delivery of the existing Android release asset."""
import io
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, make_response, send_file

android_download = Blueprint('android_download', __name__)
# Matches .github/workflows/android.yml on build/medlist-native-apk.
APK_FILENAME = 'MedList-Native.apk'
APK_URL = ('https://github.com/jashanlal25/Advaned_med_list_processor/'
           'releases/download/native-latest/' + APK_FILENAME)
MAX_APK_BYTES = 32 * 1024 * 1024


@android_download.route('/download/android', methods=['GET'])
def download_android():
    # Intentionally public: no session, login decorator or user credentials.
    # Follow upstream redirects on the server; never forward Location headers.
    upstream_request = Request(APK_URL, headers={
        'User-Agent': 'MedList-APK-Download',
        'Accept': 'application/octet-stream',
    })
    try:
        with urlopen(upstream_request, timeout=20) as upstream:
            if upstream.status != 200:
                raise ValueError('Unexpected upstream status')
            data = upstream.read(MAX_APK_BYTES + 1)
            expected = upstream.headers.get('Content-Length')
            if (len(data) > MAX_APK_BYTES or not data.startswith(b'PK\x03\x04')
                    or (expected is not None and len(data) != int(expected))):
                raise ValueError('Invalid or incomplete APK response')
    except (URLError, OSError, ValueError, HTTPException) as error:
        current_app.logger.warning('APK download failed (%s)', type(error).__name__)
        response = make_response('Android download is temporarily unavailable. Please try again.', 502)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Retry-After'] = '30'
        return response

    response = send_file(io.BytesIO(data),
                         mimetype='application/vnd.android.package-archive',
                         as_attachment=True, download_name=APK_FILENAME,
                         conditional=False, etag=False)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
