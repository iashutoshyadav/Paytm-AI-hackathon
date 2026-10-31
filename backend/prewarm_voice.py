"""Generate and cache Hindi voice for every fixed message in the demo, so 🔊 plays instantly even on bad Wi-Fi.

Run once before presenting: python prewarm_voice.py
Costs Sarvam credits only for messages not already cached (Bulbul: Rs 3 per 1,000 characters).
"""
import os
import sys

import autonomy
import sarvam_client as s
from stories import STORIES

sys.stdout.reconfigure(encoding="utf-8")

texts = []
for mid, story in STORIES.items():
    texts += [reply for _, reply, _ in story["backup_script"]]
    fake_state = {"merchant_id": mid, "merchant_name": story["name"], "cause": story["cause"]}
    for intent in autonomy.INTENTS_WITH_TEMPLATES:
        texts.append(autonomy._reply_for(fake_state, intent))
texts = list(dict.fromkeys(t for t in texts if t))  # unique, keep order

todo = [t for t in texts if not os.path.exists(s.tts_cache_path(t))]
chars = sum(len(t) for t in todo)
print(f"{len(texts)} fixed messages, {len(texts) - len(todo)} already cached.")
print(f"Generating {len(todo)} ({chars:,} characters, about Rs {chars * 3 / 1000:.0f} of credits)...")
for i, t in enumerate(todo, 1):
    try:
        s.text_to_speech(t)
        print(f"  {i}/{len(todo)} ok   {t[:60]}")
    except s.SarvamError as e:
        print(f"  {i}/{len(todo)} FAIL {e}")
print("Done. Cached audio is in backend/out/tts_cache/")
