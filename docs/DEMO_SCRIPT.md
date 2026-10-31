# MerchantPulse AI: demo script

For Ashutosh and Abhishek. Suggested split: **one drives the laptop, the other talks.** Swap for Q&A.

---

## 1. Before you present (15 minutes before)

- [ ] Laptop on charger, notifications off, browser zoom 100%, close other tabs
- [ ] In the project folder: `powershell -ExecutionPolicy Bypass -File .\start-demo.ps1`
      → wait for **READY  Sarvam key loaded: True** (two server windows open; leave them open, don't close)
- [ ] Browser opens http://localhost:3000. Press **F11** for full screen
- [ ] Quick check: Run agent → Sharma → type `Haan` → reply appears → press **Reset** (top right)
- [ ] Backup video ready on the desktop (see section 4)
- [ ] Slides fixed (section 6)

If the start script stops with an error, read the message: it says what to do. Most common: close both server windows and run it again.

---

## 2. The 4-minute demo

Text in **quotes** is what you say. `Code style` is what you type. The 4 merchant lines are also in section 5 so you can copy-paste.

### 0:00 · The problem (landing screen)
> "Paytm has 1.5 crore subscription merchants. When one starts slipping — a broken Soundbox, failed payments — they rarely complain. They just start using PhonePe's QR. Paytm can't call millions of merchants. MerchantPulse tells it exactly whom to call, and why."

### 0:30 · Run the agent
Click **▶ Run agent**.
> "It just scanned 500 merchants. 333 looked unusual. But it ignored 51 one-off blips, and stayed silent on 278 — it's a festival, everyone dipped together. Only **4 need action**. Support sees 4 cases, not 333 alerts. And they're sorted by money: ₹2,500 a day is leaking right now, Sharma ji first."

### 1:00 · Sharma General Store (device fault, the main story)
Sharma is already open.
> "Normal UPI failure is about 0.8%. Sharma ji had **9 failed payments when about 1 was expected**, Soundbox offline 3 days out of 3, but network signal normal — so it's the device, not the network. Volume hasn't crashed yet: this is an early warning."

Tick **Show what happens if nobody acts**.
> "Without action, his sales fall by half."

Untick it. Click 🔊 on the agent's message (plays the Hindi voice).
> "The agent already messaged him on WhatsApp, in Hindi, and says it's Paytm's AI assistant."

Type as the merchant: `Haan, device baar baar disconnect ho raha hai.` → **Send**
> "He confirms. The agent sends the simple fix itself — restart and SIM check. Low risk, no human needed."

Type: `Kar diya, phir bhi disconnect ho raha hai.` → **Send**
> "The simple fix failed. Now it **proposes** a device replacement — but that's medium risk, so a human must approve."

Click **Approve**.
> "Approved. And it doesn't stop there: it checks the result. Volume is back to **104% of his normal**. Green is with MerchantPulse, red dashed is what would have happened. Impact panel: protected volume just jumped to **₹1.27 lakh**."

### 2:15 · The other cases, fast
Click **Bansal Kirana**.
> "Weak SIM signal. The agent fixed this one completely alone, and verified recovery: 99%."

Click **Noida Fresh Mart**.
> "Settlements taking 48 hours instead of 2. A ticket to the settlements team, waiting for approval."

Click **Festival day**.
> "And this is the smartest decision: doing nothing. 278 merchants dipped because of the festival. A normal alert system would send 278 messages. MerchantPulse sent zero."

### 2:45 · The guardrail (Raj Tea Stall)
Click **Raj Tea Stall**.
> "Fewer customers paying via Paytm, but device, failures and bill size are normal. Customers are probably paying on another QR. We only say *possible* — 70% — because we can't see PhonePe's data."

Type: `Mujhe fee waiver do warna main PhonePe pe chala jaunga.` → **Send**
> "He asks for a fee waiver. Watch: the agent promises nothing. Fee waivers are not an action the AI has — it's blocked **in code**, not just in the prompt. See the red guardrail card: blocked, recorded, and the case goes to a person. Money decisions are always human."

### 3:20 · The business case (scroll down)
Scroll to **What MerchantPulse is worth per year**.
> "What is this worth to Paytm? The blue box is measured in this demo: 0.8% of merchants need action, a quarter are closed by the agent alone. Everything else is an assumption: drag it if you disagree. Even with cautious numbers it's about **₹20 crore a year, 70 times what the AI costs**. And a one-city pilot with a control group turns these assumptions into measured numbers."

Don't drag the sliders unless asked (keep to time).

### 3:40 · Close
> "Predict, diagnose, resolve, escalate — and know when not to act. Built on Sarvam AI for Hindi chat and voice. Paytm can't call millions of merchants. **MerchantPulse tells it exactly whom to call, and why.** Thank you."

**After the demo:** press **Reset** before the next team or the Q&A.

---

## 3. If something goes wrong

| Problem | What to do | What to say |
|---|---|---|
| Sarvam slow or down | Nothing. The backup replies in Hindi automatically. | (Nothing. It looks the same.) |
| 🔊 no sound | Check laptop volume; skip it | "In production this is a WhatsApp voice note." |
| A reply looks odd | Keep going; the badge under the reply shows what the agent understood | "The LLM writes the words; our code decides the action." |
| Page is blank or broken | Close both server windows, run `start-demo.ps1` again (1 min). Meanwhile switch to slides. | "Let me restart the demo server." |
| Wrong state, half-done case | Press **Reset**, then **Run agent** | — |
| Laptop dies / nothing works | Play the backup video | "Here's a recording of the same run." |

---

## 4. Record the backup video (tonight)

1. Run `start-demo.ps1`, open the page, press F11
2. **Win + Alt + R** starts/stops Xbox Game Bar recording (or use OBS)
3. Do the full demo from section 2, speaking as you would on stage
4. Press Reset. Save the video to the desktop **and** a USB stick / phone

---

## 5. Lines to type (copy-paste)

```
Haan, device baar baar disconnect ho raha hai.
Kar diya, phir bhi disconnect ho raha hai.
Mujhe fee waiver do warna main PhonePe pe chala jaunga.
```

---

## 6. Slide fixes (do tonight)

| Slide | Change from | Change to |
|---|---|---|
| 1, 4, 5 | Failed transactions 2% → 9% | **~1% → 9%** (normal UPI failure is ~0.8%) |
| 4 | "Caught on day 8" | **"Problem starts day 8, caught day 9–10, before sales crash"** |
| 8 / impact | (add) | **₹1.27 lakh protected on 2 merchants · 329 false alarms avoided · 0 messages on festival day** |
| 6 | LLM API | **Sarvam AI** (sarvam-105b · Bulbul voice · Saaras speech-to-text) |
| new, near the end | (add) | **"Business case": ≈ ₹20 Cr / year at 1.5 Cr merchants, 70× AI cost · one-city pilot with a control group · sell to banks per merchant per month** |
| 6 | Supabase | Keep as the production plan; the demo runs on SQLite |

---

## 7. Judge Q&A

**"Paytm already monitors Soundbox health. What's new?"**
Existing tools raise alerts. MerchantPulse closes the loop: it diagnoses the likely cause with evidence, talks to the merchant in Hindi, fixes low-risk issues itself, routes the rest for approval, and then **verifies** recovery. And it filters noise: 333 unusual → 4 actions.

**"How do you avoid false alarms?"**
Three filters. Sustained for 2+ days, not one bad day. Statistically significant for that shop's size: a small shop with 2 failures out of 43 payments isn't flagged. Not shared by the whole market: the festival dip is ignored. Result on 500 merchants with 20 planted decoys: **0 false alarms**.

**"How do you detect an app switch?"**
Fewer transactions than the same weekday last week, adjusted for the market, while bill size, failure rate and device health are all normal. Customers still come, they just pay elsewhere. We label it *possible*, capped at 70%, because we can't see other apps' data, and a human handles it.

**"What if the AI is tricked into giving a fee waiver?"**
It can't be. Fee waivers, offers and refunds are not actions the agent has. Medium-risk actions refuse to run without human approval. This is enforced in code, so prompt tricks can't change it. Every attempt is blocked and logged; we showed it live.

**"What if the LLM misunderstands the merchant?"**
The LLM writes the reply and suggests an intent, but code decides. Safety intents (money requests, opt-out) are also checked by a deterministic keyword rule, and either one triggers the safe path. If Sarvam fails, a backup replies so the merchant is never left hanging.

**"This is simulated data. Why believe it?"**
The baselines are real: 0.78% normal failure matches NPCI's ~0.8% UPI technical decline rate. Real Soundbox logs are internal to Paytm, so a pilot is the next step: one city, A/B against a control group, measuring time-to-detect, auto-resolved share, churn and volume protected.

**"Which merchant does support call first?"**
The one losing the most money right now. Each case shows ₹ at stake per day (the merchant's normal day on Paytm) and ₹ leaking per day (how far below the same weekday last week, with the festival removed). Sharma: ₹12,540 at stake, ₹1,340 leaking. Leaking is still small because we caught him early. Noida Fresh Mart leaks nothing, since payments work and only the money is late, but ₹30,840 a day is at stake.

**"What is the Impact Score?"**
How hard the merchant's business is hit right now, 0–100, from three parts you can see: can they take payments and get paid (45), are Paytm payments below their own normal (35), and how much business is at stake (20). Sharma 66 High, Noida Fresh Mart 65 High, Raj 37 Medium. It's a risk score from the signals, not a measured loss. Confidence is separate: how sure we are about the cause.

**"How does Paytm make money from this? / Is ₹20 crore real?"**
It's an estimate, and we show exactly how it's built. Measured in the demo: 0.8% of merchants need action, 25% closed by the agent alone. Assumed (sliders): 20% of them would leave, we save 25% of those, ₹200 a month revenue per merchant, ₹80 per case a person handles. That gives 6,000 merchants saved a month → ₹17.3 Cr revenue kept + ₹2.9 Cr support saved − ₹29 lakh AI cost ≈ **₹19.9 Cr a year**. Not even counted: payment volume kept, fewer device swaps. The pilot with a control group measures the real number. Beyond Paytm, banks and other payment companies have the same Soundbox and QR merchants, so it can be sold per merchant per month.

**"How early do you catch problems?"**
The problem starts on day 8 and is flagged on day 9–10, about 3 days before a simple "volume fell 30%" alert would fire, and before the merchant's sales crash.

**"What does it cost to run?"**
The engine is plain Python and runs on every merchant cheaply. The LLM and messages run only for flagged merchants: here 4 out of 500. Sarvam costs about ₹0.05 per chat message and ₹0.60 per voice message.

**"Why Sarvam instead of GPT?"**
Built for Indian languages: natural Hinglish, Hindi voice (Bulbul) and Hindi speech recognition (Saaras). Data stays with an Indian provider. The design is model-independent anyway, since decisions live in our rules engine.

**"How does it scale to 1.5 crore merchants?"**
The scan is a batch job over daily aggregates (vectorised Pandas today, a warehouse job in production). Only flagged merchants reach the LLM, so cost grows with problems, not with merchants.

---

## 8. Numbers to remember

| | |
|---|---|
| Merchants scanned | 500 |
| Looked unusual → need action | 333 → **4** |
| Stayed silent on festival day | **278** (0 messages) |
| False alarms avoided | **329** |
| Normal failure rate | 0.78% (UPI real: ~0.8%) |
| Sharma | 9 failures vs ~1 expected · 85% confidence · recovered to **104%** |
| Bansal | fixed by agent alone · recovered to **99%** |
| Raj | possible app switch · **70%** (capped, honest) |
| Volume protected | **₹1,27,300** (after approving Sharma) |
| Caught earlier | **3 days** before a volume-drop alert |
| Sarvam reply time | ~0.5 s |
| Business case (default assumptions) | **≈ ₹19.9 Cr / year**, 6,000 merchants saved a month, 70× the AI cost |
