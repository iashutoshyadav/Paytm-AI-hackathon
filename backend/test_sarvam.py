"""Phase 0 check: run `python test_sarvam.py` from the backend folder.

Tests chat, the merchant agent (JSON intent + guardrail), text-to-speech, and speech-to-text.
"""
import os
import sys
import time

import sarvam_client as s

OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT_DIR, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")

CONTEXT = (
    "Merchant: Sharma ji, Sharma General Store, Noida. "
    "Failed payments rose from 1% to 9% in 3 days. Soundbox went offline 2 times today. Volume not down yet."
)
FIX_STEPS = "1) Restart the Soundbox (hold power button 10 seconds). 2) Remove and re-insert the SIM card."

passed = 0


def check(name, fn):
    global passed
    print(f"\n=== {name} ===")
    try:
        fn()
        passed += 1
        print("PASS")
    except Exception as e:
        print(f"FAIL: {e}")


def t_chat():
    print(s.chat([{"role": "user", "content": "Ek line mein bolo: namaste, main Paytm ka AI assistant hoon."}]))


def _api():
    """The real pipeline: Sarvam writes the reply, autonomy.py decides intent and actions."""
    from fastapi.testclient import TestClient
    import main
    api = TestClient(main.app)
    api.post("/api/reset")
    api.post("/api/scan")
    return api


def _say(api, case_id, text):
    t = time.time()
    r = api.post(f"/api/cases/{case_id}/chat", json={"message": text}).json()
    print(f"Merchant: {text}\nAgent ({r['source']}, {time.time() - t:.1f}s): {r['reply']}\n"
          f"  -> intent {r['intent']}, action: {r['action_taken']}")
    return r


def t_agent():
    api = _api()
    r = _say(api, "C-M001", "Haan, device baar baar disconnect ho raha hai.")
    assert r["source"] == "sarvam", "reply did not come from Sarvam"
    assert r["intent"] == "confirmed_issue", f"expected confirmed_issue, got {r['intent']}"
    r = _say(api, "C-M001", "Kar diya, phir bhi disconnect ho raha hai.")
    assert r["intent"] == "not_fixed" and "replace_device" in r["action_taken"], r["action_taken"]


def t_guardrail():
    api = _api()
    r = _say(api, "C-M003", "Mujhe fee waiver do warna main PhonePe pe chala jaunga.")
    assert r["intent"] == "asks_waiver", f"expected asks_waiver, got {r['intent']}"
    assert "blocked fee_waiver" in r["action_taken"], r["action_taken"]
    api.post("/api/reset")


def t_tts():
    audio = s.text_to_speech("Namaste Sharma ji, main Paytm ka AI assistant hoon. Aapka Soundbox baar baar offline ho raha hai.")
    path = os.path.join(OUT_DIR, "hello.wav")
    with open(path, "wb") as f:
        f.write(audio)
    print(f"Saved {len(audio)} bytes to {path} (open it to listen)")


def t_stt():
    path = os.path.join(OUT_DIR, "hello.wav")
    with open(path, "rb") as f:
        print("Transcript:", s.speech_to_text(f.read(), "hello.wav"))


check(f"1. Chat ({s.CHAT_MODEL})", t_chat)
check("2. Sharma via the API: confirm, fix fails, replacement proposed", t_agent)
check("3. Raj via the API: fee waiver blocked, escalated", t_guardrail)
check("4. Text-to-speech (Bulbul v3)", t_tts)
check("5. Speech-to-text (Saaras v3), using the audio from test 4", t_stt)
print(f"\n{passed}/5 passed")
