import urllib.request
import urllib.error
import json

import os
api_key = os.environ.get("OPENAI_API_KEY", "")   # Set via environment — never hardcode

url = "https://api.openai.com/v1/models"
req = urllib.request.Request(url)
req.add_header("Authorization", f"Bearer {api_key}")

try:
    print("Testing connection to OpenAI api.openai.com...")
    with urllib.request.urlopen(req) as response:
        code = response.getcode()
        body = response.read().decode('utf-8')
        print(f"\nRESULT: SUCCESS (HTTP {code})")
        data = json.loads(body)
        models = [m['id'] for m in data.get('data', [])[:5]]
        print("Successfully authenticated! Available models sample:", models)
except urllib.error.HTTPError as e:
    print(f"\nRESULT: INVALID KEY (HTTP {e.code})")
    try:
        err_msg = json.loads(e.read().decode('utf-8'))
        print("OpenAI Error:", err_msg.get('error', {}).get('message', 'Unknown error'))
    except Exception:
        print("Raw Error Output:", e.read().decode('utf-8'))
except Exception as e:
    print(f"\nRESULT: ERROR")
    print("Failed to run test:", str(e))