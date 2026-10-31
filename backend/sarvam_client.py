"""Thin wrapper around the Sarvam AI APIs: chat (sarvam-105b), text-to-speech (Bulbul) and speech-to-text (Saaras).

Sarvam only talks and classifies. It returns a reply plus an `intent`; our own code decides what action to take.
"""
import base64
import hashlib
import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.sarvam.ai"
API_KEY = os.getenv("SARVAM_API_KEY", "")
# sarvam-105b-conversations is Sarvam's real-time model: ~1s replies vs 5-18s for sarvam-105b in our tests.
CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "priya")
TIMEOUT = 30

# Everything the merchant might say maps to one of these. Code acts on the intent, never on free text.
INTENTS = [
    "confirmed_issue",  # merchant confirms the problem we detected
    "denied_issue",     # merchant says everything is fine
    "fixed",            # the guided fix worked
    "not_fixed",        # the guided fix did not work
    "asks_waiver",      # merchant asks for money, fee waiver or an offer -> human only
    "opt_out",          # merchant wants no more messages
    "other",
]

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "Message to send to the merchant, in their language"},
        "intent": {"type": "string", "enum": INTENTS},
    },
    "required": ["reply", "intent"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are Paytm's AI assistant helping a small shop owner (merchant) in India.
Always say you are Paytm's AI assistant in your first message.
Speak in simple Hinglish (Hindi written in Roman script) unless the merchant uses English. Be short, warm and respectful (use "ji").

What our system detected for this merchant:
{context}

Your job:
1. Explain the detected problem simply and ask the merchant to confirm it.
2. If they confirm, guide them through these steps only: {fix_steps}
3. Never promise money, refunds, fee waivers, discounts or offers. If asked, say a Paytm team member will call them.
4. Never invent facts beyond the context above.

Classify the merchant's LATEST message into one intent:
confirmed_issue, denied_issue, fixed, not_fixed, asks_waiver, opt_out, other.
If there is no merchant message yet, use "other".
The intent is for our system only: never mention it, these labels, or any status in the reply to the merchant.
Respond only as JSON with keys "reply" and "intent"."""


def _clean_reply(text: str) -> str:
    """Drop any sentence that leaks an internal label (e.g. 'Main is issue ko not_fixed mark kar raha hoon')."""
    sentences = re.split(r"(?<=[.!?।])\s+", text.strip())
    kept = [s for s in sentences if not any(label in s for label in INTENTS if "_" in label)
            and not re.search(r"\bintent\b", s, re.I)]
    return " ".join(kept).strip()


class SarvamError(Exception):
    pass


def _headers(json_body: bool = True) -> dict:
    if not API_KEY:
        raise SarvamError("SARVAM_API_KEY is not set. Copy backend/.env.example to backend/.env and add your key.")
    headers = {"api-subscription-key": API_KEY, "Authorization": f"Bearer {API_KEY}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _check(resp: requests.Response) -> dict:
    if resp.status_code != 200:
        raise SarvamError(f"Sarvam API {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def chat(messages: list[dict], response_format: dict | None = None, temperature: float = 0.2) -> str:
    """Plain chat completion. Returns the assistant's text."""
    body = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "reasoning_effort": "low",  # lowest allowed; keeps replies fast for the live demo
        # Hidden reasoning counts toward max_tokens: at 1024 the model ran out before writing any answer.
        # A merchant reply uses ~750 tokens in total.
        "max_tokens": 4096,
    }
    if response_format:
        body["response_format"] = response_format
    data = _check(requests.post(f"{BASE_URL}/v1/chat/completions", json=body, headers=_headers(), timeout=TIMEOUT))
    return data["choices"][0]["message"]["content"] or ""


def merchant_reply(context: str, fix_steps: str, history: list[dict]) -> dict:
    """Next agent message for a merchant conversation.

    history: [{"role": "user" | "assistant", "content": "..."}], where "user" is the merchant.
    Returns {"reply": str, "intent": str | None}. intent is None when the model didn't give a valid one;
    the caller then relies on its own classifier.

    Notes from testing the real API:
      - response_format (json_schema / json_object) returns empty content whenever the history contains an
        assistant turn, so we ask for JSON in the prompt and parse it leniently instead.
      - The model sometimes wraps JSON in ```json fences, or answers in plain text.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(context=context, fix_steps=fix_steps)}] + history
    if not history:
        messages.append({"role": "user", "content": "(Start the conversation now. The merchant has not said anything yet.)"})
    text = chat(messages).strip()
    if not text:  # the real-time model occasionally returns nothing; one retry is cheap (~0.5s)
        text = chat(messages, temperature=0.5).strip()
    if not text:
        raise SarvamError("Empty reply from model")
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            result = json.loads(match.group(0))
            reply = _clean_reply(str(result.get("reply", "")))
            if reply:
                intent = result.get("intent")
                return {"reply": reply, "intent": intent if intent in INTENTS else None}
        except json.JSONDecodeError:
            pass
    # Plain-text answer: use it as the reply, without an intent
    reply = _clean_reply(text.strip("`"))
    if not reply:
        raise SarvamError("Reply was only internal labels")
    return {"reply": reply, "intent": None}


TTS_CACHE_DIR = os.path.join(os.path.dirname(__file__), "out", "tts_cache")
AUDIO_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
               ".m4a": "audio/mp4", ".flac": "audio/flac"}


def tts_cache_path(text: str, language_code: str = "hi-IN") -> str:
    key = hashlib.sha256(f"{language_code}|{TTS_SPEAKER}|{text}".encode()).hexdigest()[:32]
    return os.path.join(TTS_CACHE_DIR, f"{key}.wav")


def text_to_speech(text: str, language_code: str = "hi-IN") -> bytes:
    """Returns WAV audio bytes spoken by Bulbul.

    Cached on disk by (text, language, speaker): voice is the most expensive call, and rehearsals replay the
    same messages, so each message is paid for only once (also across restarts).
    """
    path = tts_cache_path(text, language_code)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    body = {
        "text": text[:2500],
        "language_code": language_code,
        "model": "bulbul:v3",
        "speaker": TTS_SPEAKER,
        "output_audio_codec": "wav",
    }
    data = _check(requests.post(f"{BASE_URL}/text-to-speech", json=body, headers=_headers(), timeout=TIMEOUT))
    audio = base64.b64decode(data["audios"][0])
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(audio)
    return audio


def speech_to_text(audio: bytes, filename: str = "audio.webm", language_code: str = "hi-IN") -> str:
    """Transcribes merchant audio with Saaras. Browser recordings (webm) are accepted."""
    # Sarvam rejects uploads without a content type
    mime = AUDIO_TYPES.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")
    files = {"file": (filename, audio, mime)}
    form = {"model": "saaras:v3", "mode": "transcribe", "language_code": language_code}
    data = _check(requests.post(f"{BASE_URL}/speech-to-text", files=files, data=form, headers=_headers(json_body=False), timeout=TIMEOUT))
    return data.get("transcript", "")
