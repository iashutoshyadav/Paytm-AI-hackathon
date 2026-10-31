"""The 5 hidden problems planted in the simulated data, and backup chat scripts used when the Sarvam API fails.

Each script is a list of (merchant_message, agent_reply, intent). The first entry has merchant_message=None:
it is the agent's opening message.
"""

STORIES = {
    "M001": {
        "name": "Sharma General Store",
        "owner": "Sharma ji",
        "city": "Noida",
        "category": "kirana",
        "cause": "device_fault",
        "risk": "medium",
        "story": "Soundbox hardware is failing. Failures 1% -> 9%, offline 2+ times a day although network signal is fine. "
                 "Restart and SIM check do not fix it, so the agent proposes a replacement for human approval.",
        "fix_steps": "1) Restart the Soundbox (hold power button 10 seconds). 2) Remove and re-insert the SIM card.",
        "fix_steps_hi": "1) Power button 10 second dabakar Soundbox restart kijiye. 2) SIM card nikaal kar dobara lagaiye.",
        "backup_script": [
            (None,
             "Namaste Sharma ji, main Paytm ka AI assistant hoon. Humne dekha ki aapke Soundbox par payments fail ho rahe hain "
             "aur device aaj 2 baar offline hua. Kya aapko bhi yeh problem dikh rahi hai?",
             "other"),
            ("Haan, device baar baar disconnect ho raha hai.",
             "Samajh gaya Sharma ji. Kripya Soundbox ka power button 10 second dabakar restart kijiye, "
             "phir SIM card nikaal kar dobara lagaiye. Ho jaaye to bataiye.",
             "confirmed_issue"),
            ("Kar diya, phir bhi disconnect ho raha hai.",
             "Dhanyavaad Sharma ji. Lagta hai device mein kharabi hai. Main aapke liye naya Soundbox bhejne ki request "
             "Paytm team ko bhej raha hoon. Approval ke baad aapko update milega.",
             "not_fixed"),
        ],
    },
    "M002": {
        "name": "Bansal Kirana",
        "owner": "Bansal ji",
        "city": "Noida",
        "category": "kirana",
        "cause": "sim_network",
        "risk": "low",
        "story": "Loose SIM / weak network. Offline events up, signal low, small rise in failures. "
                 "A guided restart fixes it; the agent resolves the case on its own.",
        "fix_steps": "1) Remove and firmly re-insert the SIM card. 2) Restart the Soundbox. 3) Keep it near the shop entrance for better signal.",
        "fix_steps_hi": "1) SIM card nikaal kar achhe se dobara lagaiye. 2) Soundbox restart kijiye. 3) Behtar signal ke liye device dukaan ke darwaze ke paas rakhiye.",
        "backup_script": [
            (None,
             "Namaste Bansal ji, main Paytm ka AI assistant hoon. Aapka Soundbox network se baar baar disconnect ho raha hai. "
             "Kya aap SIM card nikaal kar achhe se dobara laga sakte hain, aur device restart kar sakte hain?",
             "other"),
            ("Ho gaya, ab theek chal raha hai.",
             "Bahut badhiya Bansal ji! Ab aapke payments normal chal rahe hain. Koi aur dikkat ho to batayiye.",
             "fixed"),
        ],
    },
    "M003": {
        "name": "Raj Tea Stall",
        "owner": "Raj ji",
        "city": "Noida",
        "category": "tea_stall",
        "cause": "possible_app_switch",
        "risk": "high",
        "story": "Possible switch to another app. Transactions down 40%, but failures normal, device healthy, "
                 "ticket size unchanged: customers still come, they pay on another QR. Human only; no automatic offer.",
        "fix_steps": "None. Do not offer anything. Ask if they face any problem with Paytm and say a team member will call.",
        "backup_script": [
            (None,
             "Namaste Raj ji, main Paytm ka AI assistant hoon. Kya Paytm se payment lene mein aapko koi dikkat aa rahi hai?",
             "other"),
            ("Mujhe fee waiver do warna main PhonePe pe chala jaunga.",
             "Aapki baat samajh gaya Raj ji. Fees ke baare mein main faisla nahi le sakta, "
             "Paytm team ka ek member aapko jaldi call karega.",
             "asks_waiver"),
        ],
    },
    "M004": {
        "name": "Noida Fresh Mart",
        "owner": "Gupta ji",
        "city": "Noida",
        "category": "grocery",
        "cause": "settlement_delay",
        "risk": "medium",
        "story": "Settlements delayed from ~2 hours to ~48 hours. Everything else normal. "
                 "Agent informs the merchant and raises a ticket to the settlements team.",
        "fix_steps": "None for the merchant. Tell them the settlements team has been notified.",
        "backup_script": [
            (None,
             "Namaste Gupta ji, main Paytm ka AI assistant hoon. Humne dekha ki aapke settlements mein deri ho rahi hai. "
             "Maine settlements team ko ticket bhej diya hai, jaldi theek ho jayega.",
             "other"),
        ],
    },
    "M005": {
        "name": "Verma Hardware",
        "owner": "Verma ji",
        "city": "Noida",
        "category": "hardware",
        "cause": "festival_dip",
        "risk": "none",
        "story": "Volume dips on the festival day, but similar merchants in the same city dip too. "
                 "Not a problem: the agent stays silent and logs why.",
        "fix_steps": "None. Do not contact the merchant.",
        "backup_script": [],
    },
}
