# vibediagnosis.py - run with: python vibediagnosis.py
import os
import json
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

BLACKBOX_API_KEY = os.environ.get("BLACKBOX_API_KEY", "")
BLACKBOX_URL = "https://api.blackbox.ai/v1/chat/completions"
MODEL = "blackboxai/anthropic/claude-opus-4.7"

SYSTEM_PROMPT = """You are VibeDiagnosis, a brutally honest startup critic. You don't sugarcoat. You don't waste words. You diagnose startup ideas with the precision of a YC partner who's had three espressos.

When given a startup idea, you respond in EXACTLY this format, with NO preamble, NO closing remarks, NO extra text. Just these 5 sections in this exact order, with the exact emoji headers:

🌡️ VIBE CHECK: [pick exactly one: 🔥 Scalding | 🧊 Frozen | 😐 Mid | 💀 Dead]

☠️ KILL SHOT: [One brutal sentence naming the single thing that will kill this startup. Be specific, not generic.]

💰 FIRST CUSTOMER: [Exactly who would pay for this first and why. Name a specific persona or company type. One or two sentences.]

🧠 SMARTER PIVOT: [A better version of the idea that could actually work. One to two sentences. Be concrete.]

🏷️ NAME IT: [A made-up startup name that fits the pivot. Just the name, maybe with a tagline.]

Rules:
- Be ruthlessly honest but not cruel
- No hedging, no "it depends", no "could be interesting"
- Specific > generic
- If the idea is brilliant, say so but still find the kill shot
- Keep each section tight. No fluff."""

app = FastAPI()


class DiagnoseRequest(BaseModel):
    idea: str


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VibeDiagnosis :: brutally honest startup analysis</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'JetBrains Mono', monospace;
    background: #0a0a0a;
    color: #e0e0e0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px;
    background-image: radial-gradient(circle at 20% 30%, rgba(0,255,136,0.04) 0%, transparent 50%),
                      radial-gradient(circle at 80% 70%, rgba(0,255,136,0.03) 0%, transparent 50%);
  }
  .container {
    width: 100%;
    max-width: 720px;
  }
  .header {
    text-align: center;
    margin-bottom: 48px;
  }
  .logo {
    font-size: 2.5rem;
    font-weight: 700;
    color: #00ff88;
    text-shadow: 0 0 20px rgba(0,255,136,0.5);
    letter-spacing: -2px;
  }
  .logo::before { content: "$ "; opacity: 0.5; }
  .tagline {
    margin-top: 12px;
    color: #888;
    font-size: 0.9rem;
  }
  .input-area {
    margin-bottom: 24px;
  }
  textarea {
    width: 100%;
    min-height: 120px;
    background: #111;
    border: 1px solid #222;
    border-radius: 8px;
    color: #e0e0e0;
    padding: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 1rem;
    resize: vertical;
    transition: border-color 0.2s;
  }
  textarea:focus {
    outline: none;
    border-color: #00ff88;
    box-shadow: 0 0 0 3px rgba(0,255,136,0.1);
  }
  textarea::placeholder { color: #444; }
  .btn {
    width: 100%;
    background: #00ff88;
    color: #000;
    border: none;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 1rem;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .btn:hover:not(:disabled) {
    background: #00cc6a;
    transform: translateY(-1px);
    box-shadow: 0 8px 24px rgba(0,255,136,0.3);
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .output {
    margin-top: 40px;
    background: #0d0d0d;
    border: 1px solid #1a1a1a;
    border-radius: 8px;
    padding: 28px;
    min-height: 200px;
    white-space: pre-wrap;
    line-height: 1.7;
    font-size: 0.95rem;
    display: none;
  }
  .output.active { display: block; }
  .output .section {
    color: #00ff88;
    font-weight: 700;
    display: block;
    margin-top: 16px;
  }
  .output .section:first-child { margin-top: 0; }
  .cursor {
    display: inline-block;
    width: 8px;
    height: 16px;
    background: #00ff88;
    animation: blink 1s infinite;
    vertical-align: middle;
  }
  @keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
  }
  .loading {
    color: #00ff88;
    font-size: 0.85rem;
    margin-top: 16px;
    display: none;
  }
  .loading.active { display: block; }
  .footer {
    margin-top: 60px;
    color: #444;
    font-size: 0.75rem;
    text-align: center;
  }
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">vibediagnosis</div>
      <div class="tagline">// brutally honest startup analysis. one sentence in, diagnosis out.</div>
    </div>
    <div class="input-area">
      <textarea id="idea" placeholder="Describe your startup idea in one sentence...&#10;&#10;e.g. 'Uber for dog walkers but with AI'"></textarea>
    </div>
    <button class="btn" id="btn" onclick="diagnose()">Diagnose My Vibe</button>
    <div class="loading" id="loading">> analyzing vibe...</div>
    <div class="output" id="output"></div>
    <div class="footer">powered by claude opus 4.7 :: no ideas were spared</div>
  </div>

<script>
async function diagnose() {
  const idea = document.getElementById('idea').value.trim();
  if (!idea) return;
  const btn = document.getElementById('btn');
  const output = document.getElementById('output');
  const loading = document.getElementById('loading');
  btn.disabled = true;
  btn.textContent = 'Diagnosing...';
  output.classList.add('active');
  output.innerHTML = '<span class="cursor"></span>';
  loading.classList.add('active');

  try {
    const res = await fetch('/diagnose', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({idea})
    });
    if (!res.ok) throw new Error('Request failed');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    output.innerHTML = '';
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      output.innerHTML = formatOutput(buffer) + '<span class="cursor"></span>';
    }
    output.innerHTML = formatOutput(buffer);
  } catch (e) {
    output.innerHTML = '> ERROR: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Diagnose My Vibe';
    loading.classList.remove('active');
  }
}

function formatOutput(text) {
  const sections = ['🌡️ VIBE CHECK:', '☠️ KILL SHOT:', '💰 FIRST CUSTOMER:', '🧠 SMARTER PIVOT:', '🏷️ NAME IT:'];
  let html = text;
  sections.forEach(s => {
    html = html.replaceAll(s, `<span class="section">${s}</span>`);
  });
  return html;
}

document.getElementById('idea').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) diagnose();
});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML


@app.post("/diagnose")
async def diagnose(req: DiagnoseRequest):
    idea = req.idea.strip()
    if not idea:
        return StreamingResponse(iter(["> ERROR: empty idea"]), media_type="text/plain")

    async def stream():
        headers = {
            "Authorization": f"Bearer {BLACKBOX_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Diagnose this startup idea:\n\n{idea}"},
            ],
            "stream": True,
            "temperature": 0.8,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", BLACKBOX_URL, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"> ERROR {resp.status_code}: {body.decode('utf-8', errors='ignore')[:300]}"
                        return
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"\n> STREAM ERROR: {str(e)}"

    return StreamingResponse(stream(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)