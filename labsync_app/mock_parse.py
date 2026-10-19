"""Rule-based request reader for the offline mock Lab Agent.

The mock has exact answers for the few-shot and eval sentences. For anything else typed in the
web app or CLI it falls back to these keyword rules, so a plain request like "plate reader
Monday at 10 for 45 minutes" works offline. This is a stand-in for the model, not a model: it
only knows the synthetic catalog's instruments and supplies and simple dates and times, and it
follows the Lab Agent prompt's parsing rules (no time means 09:00-17:00, missing duration means
60 minutes plus a missing-information note, a past date is refused). The output still goes
through plan_create_draft's validation like any model output.
"""
import re
from datetime import date, datetime, timedelta

INSTRUMENTS = [  # (pattern, capabilities, title); first match wins
    (r"confocal", ["confocal_imaging"], "Confocal imaging"),
    (r"widefield|wide-field|fluorescence microscope|\bmicroscope\b", ["widefield_imaging"], "Widefield imaging"),
    (r"flow cytometer|cytometer|\bflow\b|\bfacs\b", ["flow_analysis"], "Flow cytometry"),
    (r"plate reader", ["fluorescence_plate_read"], "Plate reading"),
    (r"q?pcr|thermal cycler|thermocycler", ["pcr"], "PCR run"),
    (r"centrifuge|spin down", ["high_g_centrifugation"], "Centrifugation"),
    (r"sequenc", ["sequencing"], "Sequencing run"),
]
SUPPLIES = [
    (r"anti-?gfp|antibod", "ANTI_GFP_100"), (r"coverslip", "COVERSLIP_24"), (r"\bpbs\b", "PBS_1L"),
    (r"\btips?\b", "TIPS_200"), (r"15 ?ml tubes?|\btubes?\b", "TUBES_15"), (r"dapi", "DAPI_1ML"),
    (r"dna (isolation |extraction )?kits?", "DNA_KIT"), (r"pcr plates?", "PCR_PLATES"),
]
WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "couple": 2,
         "a couple": 2, "half": 0.5, "a few": 3, "few": 3}
NUM = r"(\d+(?:\.\d+)?|a couple|a few|an|a|one|two|three|four|five|six|half)"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _n(token):
    token = token.strip()
    return float(token) if re.match(r"^\d", token) else WORDS.get(token, 1)


def _offset(day):
    return "-06:00" if day >= date(2026, 11, 1) else "-05:00"  # America/Chicago, DST ends Nov 1 2026


def _iso(day, minutes):
    return "%sT%02d:%02d:00%s" % (day.isoformat(), minutes // 60, minutes % 60, _offset(day))


def _day(text, today):
    if re.search(r"\b(tomorrow|tmrw|tmr)\b", text):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", text):
        return today
    if re.search(r"\byesterday\b", text):
        return today - timedelta(days=1)
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})\b", text)
    if m:
        return date(today.year, MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
    if m:
        return date(today.year, int(m.group(1)), int(m.group(2)))
    for i, name in enumerate(DAYS):
        if re.search(r"\b%s|\b%s\b" % (name, name[:3]), text):
            ahead = (i - today.weekday()) % 7 or 7
            if "next " + name in text and ahead < 7 and today.weekday() < i:
                ahead += 7
            return today + timedelta(days=ahead)
    return None


def _time(text):
    """(start minute, window end minute or None)."""
    m = re.search(r"\b(\d{1,2})(?::(\d\d))?\s*(am|pm)?\s*(?:-|to|until)\s*(\d{1,2})(?::(\d\d))?\s*(am|pm)\b", text)
    if m:
        h1, h2 = int(m.group(1)), int(m.group(4))
        ap2 = m.group(6)
        ap1 = m.group(3) or ap2
        h1 = h1 + 12 if ap1 == "pm" and h1 < 12 else h1
        h2 = h2 + 12 if ap2 == "pm" and h2 < 12 else h2
        return h1 * 60 + int(m.group(2) or 0), h2 * 60 + int(m.group(5) or 0)
    m = re.search(r"\b(\d{1,2})(?::(\d\d))?\s*(am|pm)\b", text) or re.search(r"\b(?:at|@)\s*(\d{1,2})(?::(\d\d))?()\b", text) \
        or re.search(r"\b(\d{1,2}):(\d\d)()\b", text)
    if m:
        h = int(m.group(1))
        ap = m.group(3)
        if ap == "pm" and h < 12:
            h += 12
        elif not ap and h < 8:
            h += 12  # "at 2" in a lab means 14:00
        return h * 60 + int(m.group(2) or 0), None
    if re.search(r"\bmorning\b|\bam\b", text):
        return 9 * 60, 13 * 60
    if re.search(r"\bafternoon\b|\bpm\b", text):
        return 13 * 60, 17 * 60
    return None


def _duration(text):
    if re.search(r"\ball day\b|\bfull day\b", text):
        return 480
    m = re.search(NUM + r"\s*-?\s*(?:hours?|hrs?|h)\b", text)
    if m:
        extra = 30 if re.search(r"and a half", text[m.end():m.end() + 12]) else 0
        return int(round(_n(m.group(1)) * 60)) + extra
    m = re.search(NUM + r"\s*-?\s*(?:minutes?|mins?|m)\b", text)
    if m:
        return int(round(_n(m.group(1))))
    return None


def _round15(minutes):
    return -(-minutes // 15) * 15


def _supplies(text):
    out = []
    for pattern, sku in SUPPLIES:
        m = re.search(r"(?:\b" + NUM + r"\s+(?:\w+\s+){0,3}?)?(?:" + pattern + r")", text)
        if m:
            qty = _n(m.group(1)) if m.group(1) else 1
            out.append({"skuId": sku, "quantity": max(1, int(qty)), "source": "stated" if m.group(1) else "inferred"})
    return out


def parse(text, actor_id, lab_id, now_iso):
    """Return a ParsedGoal dict, or None if the text names no instrument and no supply."""
    t = " " + re.sub(r"\s+", " ", text.lower()) + " "
    today = datetime.fromisoformat(now_iso).date()
    instrument = next(((caps, title) for pat, caps, title in INSTRUMENTS if re.search(pat, t)), None)
    supplies = _supplies(t)
    if not instrument and not supplies:
        return None
    missing, steps = [], []
    start = end = None
    if instrument:
        caps, title = list(instrument[0]), instrument[1]
        if "gfp" in t and caps[0] in ("confocal_imaging", "widefield_imaging"):
            caps = sorted(caps + ["gfp_imaging"])
            title = title.replace("imaging", "GFP imaging")
        duration = _duration(t)
        if duration is None:
            duration = 60
            missing.append("instrument duration")
        duration = _round15(duration)
        day = _day(t, today)
        clock = _time(t)
        if day is None:
            missing.append("desiredStart")
        elif day < today:
            missing += ["desiredStart", "date is in the past"]
        else:
            s, window_end = clock or (9 * 60, 17 * 60)
            if clock and window_end is None:
                window_end = s + duration
            start, end = _iso(day, s), _iso(day, window_end)
            if window_end - s < duration:
                missing.append("the window is shorter than the %d-minute session" % duration)
        if re.search(r"\bprep\b|prep room|prepare", t):
            steps.append({"stepId": "prep", "kind": "prep_room", "title": "Sample prep", "durationMinutes": 45,
                          "requiredCapabilities": ["wet_prep"], "dependsOn": [], "source": "stated", "required": True})
        steps.append({"stepId": "run", "kind": "instrument", "title": title, "durationMinutes": duration,
                      "requiredCapabilities": caps, "dependsOn": ["prep"] if steps else [], "source": "stated",
                      "required": True})
    summary = text.strip()
    summary = summary[:77] + "..." if len(summary) > 80 else summary
    return {"labId": lab_id, "requesterId": actor_id, "goalSummary": summary[0].upper() + summary[1:],
            "desiredStart": start, "preferredEnd": end, "deadline": None, "steps": steps,
            "requiredCapabilities": [], "supplies": supplies, "missingInformation": missing, "confidence": 0.6}
