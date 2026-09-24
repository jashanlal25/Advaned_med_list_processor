from flask import Blueprint, request, jsonify
import urllib.request
import urllib.error
import json

chatbot_bp = Blueprint('chatbot', __name__)

PROVIDERS = {
    'groq': ('https://api.groq.com/openai/v1/chat/completions', 'llama-3.1-8b-instant'),
    'openai': ('https://api.openai.com/v1/chat/completions', 'gpt-4o-mini'),
    'openrouter': ('https://openrouter.ai/api/v1/chat/completions', 'openrouter/free'),
}

SYSTEM_PROMPT = (
    "You are a medicine discount-list editor. "
    "Items format: name|disc%. "
    "For analysis: answer in plain text. "
    "For bulk changes: return ONLY the updated list in name|disc% format, one item per line."
)


def _error_message(exc):
    try:
        detail = json.loads(exc.read().decode('utf-8', errors='replace'))
        error = detail.get('error', {})
        message = error.get('message', '') if isinstance(error, dict) else str(error)
        # Do not reflect arbitrary upstream data, which could include credentials.
        return str(message)[:240] if message else 'Provider rejected the request'
    except (ValueError, TypeError):
        return 'Provider rejected the request'


def _provider_and_key(data):
    if not isinstance(data, dict):
        return None, None, (jsonify({'error': 'Invalid request'}), 400)
    provider = data.get('provider', 'groq')
    key = data.get('apiKey', '')
    if provider not in PROVIDERS:
        return None, None, (jsonify({'error': 'Unsupported provider'}), 400)
    if not isinstance(key, str) or not key.strip() or len(key) > 512 or '\n' in key or '\r' in key:
        return None, None, (jsonify({'error': 'A valid API key is required'}), 400)
    return provider, key.strip(), None


@chatbot_bp.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@chatbot_bp.route('/chatbot/grok', methods=['POST'])
def grok_chat():
    data = request.get_json(silent=True) or {}
    provider, api_key, error = _provider_and_key(data)
    if error:
        return error

    raw_payload = data.get('rawPayload')
    if raw_payload and isinstance(raw_payload, dict):
        payload = raw_payload.copy()
    else:
        command = (data.get('command') or '').strip()
        items = data.get('items', [])
        if not command or len(command) > 2000 or not isinstance(items, list) or len(items) > 5000:
            return jsonify({'error': 'Invalid command or item list'}), 400
        compact = '\n'.join(f"{it['name']}|{it['disc']}%" for it in items if isinstance(it, dict) and it.get('name'))
        user_msg = (f"Current list:\n{compact}\n\n" if compact else '') + f"Command: {command}"
        payload = {
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': user_msg},
            ],
            'max_tokens': 1200,
            'temperature': 0.1,
        }

    # The application chooses the provider's model. A client cannot submit an
    # unexpectedly expensive model in rawPayload.
    payload['model'] = ('openai/gpt-4o-mini' if provider == 'openrouter' and data.get('modelTier') == 'paid' else PROVIDERS[provider][1])
    payload['max_tokens'] = min(4000, max(1, int(payload.get('max_tokens', 1200))))
    req = urllib.request.Request(
        PROVIDERS[provider][0],
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read())
            reply = body['choices'][0]['message']['content']
            return jsonify({'reply': reply, 'usage': body.get('usage', {})})
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            return jsonify({'error': _error_message(exc), 'code': exc.code}), exc.code
        return jsonify({'error': _error_message(exc), 'code': exc.code}), 502
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return jsonify({'error': 'Could not complete the provider request'}), 502


@chatbot_bp.route('/chatbot/usage', methods=['POST'])
def chatbot_usage():
    data = request.get_json(silent=True) or {}
    provider, api_key, error = _provider_and_key(data)
    if error:
        return error
    if provider == 'openai':
        return jsonify({
            'available': False,
            'message': 'OpenAI does not expose remaining account credits to a standard project API key. View usage and billing in the OpenAI Platform dashboard.'
        })
    if provider == 'groq':
        return jsonify({
            'available': False,
            'message': 'Groq does not expose a remaining quota total for this key. Rate limits may be reported when you send a message.'
        })
    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/key',
        headers={'Authorization': f'Bearer {api_key}'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read()).get('data', {})
        return jsonify({
            'available': True,
            'usage': info.get('usage'),
            'limit': info.get('limit'),
            'limit_remaining': info.get('limit_remaining'),
            'free_model_daily_requests': info.get('free_model_daily_requests'),
        })
    except urllib.error.HTTPError as exc:
        return jsonify({'error': _error_message(exc), 'code': exc.code}), exc.code if exc.code in (401, 403, 429) else 502
    except (urllib.error.URLError, TimeoutError, ValueError, TypeError):
        return jsonify({'error': 'Could not check OpenRouter usage'}), 502
