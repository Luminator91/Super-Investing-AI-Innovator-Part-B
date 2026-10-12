"""One tiny wrapper around the LLM. Everything else in the project calls only chat()/chat_json()."""
from __future__ import annotations

import json
import os
import re
import threading
import time

import requests

from config import PROVIDERS, provider_name

_PICKED: dict[str, str] = {}      # model auto-selected at runtime, per provider
_LOCK = threading.Lock()
_WINDOW: list[tuple[float, int]] = []   # (timestamp, estimated tokens) of calls in the last 60s
TPM_BUDGET = int(os.getenv("TPM_BUDGET", "6500"))   # stay under Groq's 8000 tokens/minute cap


class APIError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url}\nServer said: {body[:500]}")
        self.status, self.body = status, body


def _throttle(est_tokens: int):
    """Proactive rate limiting: wait until this call fits inside the per-minute token budget."""
    est = min(est_tokens, TPM_BUDGET)
    with _LOCK:
        while True:
            now = time.time()
            _WINDOW[:] = [(t, n) for t, n in _WINDOW if now - t < 60]
            used = sum(n for _, n in _WINDOW)
            if used + est <= TPM_BUDGET or not _WINDOW:
                _WINDOW.append((now, est))
                return
            wait = max(60 - (now - _WINDOW[0][0]) + 0.5, 1)
            print(f"[info] Token budget {used}/{TPM_BUDGET} used this minute, pausing {wait:.0f}s to stay under the free-tier limit...")
            time.sleep(min(wait, 60))


def _post(url, headers, payload, retries=8):
    """POST with backoff. If the server still says 429, wait exactly as long as it asks."""
    r = None
    for attempt in range(retries):
        r = requests.post(url, headers=headers, json=payload, timeout=600)
        if r.status_code == 429 or r.status_code >= 500:
            if "too large" in r.text.lower():      # model limit is below what one request needs
                raise APIError(r.status_code, r.text, url)
            m = re.search(r"try again in ([\d.]+)\s*(ms|s)", r.text)
            if m:
                wait = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1) + 1
            else:
                wait = float(r.headers.get("retry-after", 3 * 2 ** attempt))
            print(f"[info] HTTP {r.status_code}, waiting {wait:.0f}s then retrying ({attempt + 1}/{retries})")
            if wait > 90:
                raise APIError(r.status_code, f"Rate limit: asked to wait {wait:.0f}s. {r.text[:300]}", url)
            time.sleep(wait)
            continue
        if not r.ok:
            raise APIError(r.status_code, r.text, url)
        return r.json()
    raise APIError(r.status_code, r.text, url)


def list_models() -> list[str]:
    """Ask the provider which models your key can use."""
    cfg = PROVIDERS[provider_name()]
    if cfg["kind"] == "ollama":
        r = requests.get(f"{cfg['base_url']}/api/tags", timeout=30)
        return [m["name"] for m in r.json().get("models", [])]
    r = requests.get(f"{cfg['base_url']}/models", timeout=30,
                     headers={"Authorization": f"Bearer {os.getenv(cfg['key_env'] or '')}"})
    if not r.ok:
        raise APIError(r.status_code, r.text, f"{cfg['base_url']}/models")
    return sorted(m["id"] for m in r.json()["data"])


def _auto_pick() -> str:
    """Choose a sensible chat model from what the provider actually offers."""
    skip = ("whisper", "guard", "tts", "orpheus", "embed", "safeguard", "prompt", "playai",
            "qwen3", "kimi", "compound", "allam")
    good = [m for m in list_models() if not any(s in m.lower() for s in skip)]
    for pref in ("gpt-oss-120b", "llama-3.3-70b", "llama-3.1-70b", "llama-4", "gpt-oss-20b",
                 "llama-3.1-8b", "llama"):
        for m in good:
            if pref in m.lower():
                return m
    if not good:
        raise RuntimeError("No usable chat model found for your API key.")
    return good[0]


def model_name() -> str:
    cfg = PROVIDERS[provider_name()]
    return _PICKED.get(provider_name()) or os.getenv(cfg["model_env"]) or cfg["model"]


def chat(system: str, user: str, json_mode: bool = False, temperature: float = 0.1) -> str:
    name = provider_name()
    cfg = PROVIDERS[name]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    if cfg["kind"] == "ollama":
        # Native API, because Ollama's default context window is small and silently
        # truncates long prompts. num_ctx makes the limit explicit.
        payload = {"model": model_name(), "messages": messages, "stream": False,
                   "options": {"temperature": temperature, "num_ctx": 8192}}
        if json_mode:
            payload["format"] = "json"
        return _post(f"{cfg['base_url']}/api/chat", {}, payload)["message"]["content"]

    key = os.getenv(cfg["key_env"] or "")
    if not key:
        raise RuntimeError(f"Set the {cfg['key_env']} environment variable (see README).")
    payload = {"model": model_name(), "messages": messages, "temperature": temperature, "max_tokens": 2500}
    if "gpt-oss" in payload["model"]:
        payload["reasoning_effort"] = "low"     # less hidden thinking = faster, fewer tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    url, headers = f"{cfg['base_url']}/chat/completions", {"Authorization": f"Bearer {key}"}

    _throttle(int((len(system) + len(user)) / 3.5) + 1200)   # rough estimate: input + expected output
    try:
        data = _post(url, headers, payload)
    except APIError as e:
        wrong_model = e.status in (400, 404) and "model" in e.body.lower()
        if wrong_model and name not in _PICKED:
            _PICKED[name] = _auto_pick()
            print(f"[info] Model '{payload['model']}' unavailable. Auto-selected '{_PICKED[name]}'.")
            payload["model"] = _PICKED[name]
            data = _post(url, headers, payload)
        else:
            raise
    return data["choices"][0]["message"]["content"]


def _extract_json(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start != -1 and end != -1 else raw


def chat_json(system: str, user: str, retries: int = 2) -> dict:
    """Ask for JSON; if the model returns something unparsable, tell it and retry."""
    last = None
    strict = True
    for _ in range(retries + 2):
        try:
            raw = chat(system, user, json_mode=strict)
        except APIError as e:
            if e.status == 400 and "json_validate_failed" in e.body:
                strict = False      # provider's JSON validator rejected it; retry without strict mode
                user += "\n\nReply with ONE valid JSON object only. No Markdown, no text outside the JSON."
                last = e
                continue
            raise
        try:
            return json.loads(_extract_json(raw))
        except Exception as e:  # noqa: BLE001
            last = e
            user += "\n\nYour previous reply was not valid JSON. Reply with ONE valid JSON object only."
    raise ValueError(f"Model never returned valid JSON: {last}")