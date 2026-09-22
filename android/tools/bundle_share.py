"""Bundle the existing chooser and storage code for offline native receipt."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
s = (root / 'templates/shared_file.html').read_text()
import re
s = re.sub(r'    <link[^\n]+\n', '', s)
s = s.replace("{% include 'navbar_component.html' %}", '')
s = s.replace('padding-top: 90px;', 'padding-top: 12px;').replace('padding-top: 84px;', 'padding-top: 12px;')
s = s.replace('{{ shared_payload.filename }}', '').replace('{{ shared_payload.type }} • {{ shared_payload.size }} bytes', '')
s = s.replace('{{ shared_payload|tojson }}', '__MEDLIST_PAYLOAD__')
s = s.replace('<script src="{{ url_for(\'static\', filename=\'shared-store.js\') }}"></script>', '<script>\n' + (root / 'static/shared-store.js').read_text() + '\n</script>')
s = s.replace('Add to the Index 3-file batch', 'Keep in your 6-file batch')
s = s.replace('✓ File received', '✓ File ready on your phone')
s = s.replace("if (payload) {\n", "if (payload) {\n                document.getElementById('fname').textContent = payload.filename;\n", 1)
s = s.replace("            function commitToIndexedDB() {", "            function commitToIndexedDB() {\n                if (recordId) return Promise.resolve(recordId);")
s = s.replace("                        payload = null;\n                        payloadEl.textContent = '{}';", "                        payloadEl.textContent = '{}';")
s = s.replace("            function lockAll() {", "            function unlockAll() {\n                document.querySelectorAll('.dest-btn, .cancel-btn').forEach(b => { b.disabled = false; });\n                if (isPdf) { document.getElementById('destDiff').disabled = true; document.getElementById('destGenHtml').disabled = true; }\n                if (isPdf || isHtml) document.getElementById('destDedup').disabled = true;\n            }\n\n            function lockAll() {")
s = s.replace("                                    return SharedStore.deleteFile(id).then(function () {", "                                    return Promise.resolve().then(function () {\n                                        unlockAll();")
s = s.replace("                    console.warn('share destination failed:', err);", "                    unlockAll();\n                    console.warn('share destination failed:', err);")
assert '{{' not in s and '{%' not in s
(root / 'android/app/src/main/assets/share.html').write_text(s)
