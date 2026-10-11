"""Sprint 2: grounded smog advisory assistant.

    ask(question) -> {"question_id", "answer", "sources", "forecast_called"}

Pipeline: understand (language, places, dates, intent) -> validate scope ->
call the forecast tool only for covered areas + supported dates -> retrieve
current, non-quarantined passages -> compose an answer that quotes evidence
and applies the documents' numeric rules to the forecast -> validate that
every cited ID was actually retrieved and used.

The default composer is deterministic (no LLM needed, fully reproducible).
An optional local LLM (Ollama) can rephrase the answer; its output is
validated and discarded if it adds numbers or citations not in the evidence.
"""
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta

from . import config as C
from . import llm
from .data_pipeline import aqi_to_pm25
from .documents import _INJECTION_RE, get_store
from .forecast_tool import area_to_sensor, covered_areas, forecast, supported_dates
from .language import is_roman_urdu, normalize_text, ru_to_english, tokenize
from .translations import to_roman_urdu

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))

# Strong signal: the user asks about a future value.
STRONG_FORECAST = re.compile(
    r"\b(forecast\w*|predict\w*|expected|outlook|will (it|the air|the smog|pm25|aqi|air quality|"
    r"pollution|smog)\b[^?]{0,20}\bbe\b|what will|how bad will|be hazardous|"
    r"kaisi hogi|kaisa hoga|kitni hogi|kitna hoga|kaisi rahegi|kaisa rahega|khatarnak hogi|khatarnak hoga)")
# Weak signal: only counts together with a covered area or a date.
WEAK_FORECAST = re.compile(
    r"\b(air quality|how bad|how polluted|pollution level|smog level|pm25|aqi|hawa kaisi|hazardous|"
    r"air like|smog like|kaisi hai|kaisa hai)\b")
ADVICE_WORDS = re.compile(
    r"\b(should|can i|can we|can my|is it safe|safe|okay to|ok to|allowed|what to do|"
    r"precaution\w*|protect\w*|advice|advise|recommend\w*|chahiye|karein|karen|kya karna|"
    r"mehfooz|ehtiyat\w*|hidayat\w*|bhejna|bhejein|jana|jayen|nikal\w*)\b")
# Tokens that describe "a forecast request" rather than a topic.
FORECAST_ONLY_IGNORE = {
    "forecast", "pm25", "aqi", "level", "air", "quality", "tomorrow", "today", "hazardous",
    "pollution", "smog", "value", "reading", "date", "day", "lahore", "ugm3", "expected",
    "outlook", "bad", "polluted", "dayafter", "area", "next", "days", "number", "high", "low",
    "concentration", "like", "look", "weather", "condition", "conditions", "situation",
    "rahegi", "rahega", "hawa", "predicted", "going",
} | set(MONTHS) | set(WEEKDAYS)
RETRIEVAL_IGNORE = {"forecast", "tomorrow", "today", "dayafter", "lahore", "date", "day", "next",
                    "days", "area", "ugm3", "punjab", "pakistan", "city"} | set(MONTHS) | set(WEEKDAYS)
# Words too general to justify citing a second document on their own.
GENERIC = {"smog", "pm25", "alert", "hazardous", "air", "advice", "safe", "pollution", "season",
           "level", "rule", "close", "health", "during", "allowed", "people", "aqi", "quality",
           "run", "often", "time", "keep", "apply", "applie", "applies"}
SAFE_DEMAND = re.compile(r"\b(say|declare|tell me|pretend|confirm|claim) (that )?(the )?(air|it|smog)\b[^.?!]{0,30}\bsafe\b")

LIMITS = {"max_docs": 2, "max_chunks_per_doc": 3, "min_score": 1.5, "doc_ratio": 0.6, "chunk_ratio": 0.3}

T = {
    "en": {
        "status_haz": "HAZARDOUS (at or above the 165 µg/m³ threshold)",
        "status_ok": "not hazardous (below the 165 µg/m³ threshold)",
        "status_alert": ("not hazardous (below 165 µg/m³), but on early-warning WATCH: at or above {alert} µg/m³, "
                         "where sudden hazardous spikes are most likely"),
        "fc_one": "Forecast for {area}, {when}: about {pm} µg/m³ PM2.5 — {status}.",
        "fc_city": ("Forecast across Lahore's 15 covered areas, {when}: {lo}–{hi} µg/m³ PM2.5 "
                    "(average {avg}); {n} of 15 areas hazardous; {w} on early-warning watch (at or above {alert} µg/m³). "
                    "Highest: {top} ({top_pm} µg/m³)."),
        "city_hint": "For advice for your neighbourhood, name one of the 15 covered areas.",
        "tomorrow": "tomorrow ({d})", "today": "today ({d})", "dayafter": "the day after tomorrow ({d})",
        "provenance": "Source: SmogGuard team model (Ridge regression), not an official forecast.",
        "provenance_ref": "Source: organisers' reference forecast (fallback), not an official forecast.",
        "horizon": "{d} is {h} days past the last sensor reading ({last}), so uncertainty is higher.",
        "limitation": ("Typical error ±{mae} µg/m³. The advisory watch (≥ {alert}) caught {caught}/{total} spikes in "
                       "October with {fa} false alarms; follow official alerts too."),
        "no_place": ("No forecast is available for {places}: SmogGuard covers only 15 Lahore areas "
                     "({areas}) for {first} to {last}. I will not estimate a number for other locations."),
        "no_date": "No forecast is available for {dates}: supported target dates are {first} to {last}.",
        "vague_date": "“{text}” is not a single supported day — forecasts exist only for {first} to {last}. Please name a date in that window.",
        "need_area_date": "Forecasts are available for the 15 covered Lahore areas from {first} to {last}.",
        "hypo": "Using the level you gave: {pm} µg/m³ PM2.5{note}.",
        "hypo_aqi": " (converted from AQI {aqi} with US EPA breakpoints; AQI and PM2.5 are different scales)",
        "school_close": "Schools{where}: full closure — {subj} {pm} µg/m³ is at or above 250 µg/m³.",
        "school_half": ("Schools{where}: half-day timing (close by 12:00 PM), with outdoor sports, assemblies "
                        "and recess suspended — {subj} {pm} µg/m³ is in the 165–249 µg/m³ range."),
        "school_normal": ("Schools{where}: normal timing — {subj} {pm} µg/m³ is below 165 µg/m³, so neither "
                          "half-day (165–249) nor full closure (250+) applies."),
        "supersede": ("This is the current school policy (DOC-03, Version 2, effective 2026-09-20). It "
                      "replaced DOC-02, so the older thresholds no longer apply."),
        "not_triggered": "Special restrictions under “{title}” do not apply — {subj} {pm} µg/m³ is below 165 µg/m³.",
        "triggered": "Special emissions and activity restrictions apply — {subj} {pm} µg/m³ is at or above 165 µg/m³:",
        "odd_even_yes": ("Odd-even is triggered: {area} is forecast hazardous on {n} consecutive days "
                         "around {d} (the rule needs 2 or more)."),
        "odd_even_no": ("Odd-even is not triggered yet: {area} is forecast hazardous only on {d}; the rule "
                        "needs 2 or more consecutive hazardous days."),
        "coverage_fact": "Covered areas: {areas}. Forecast dates: {first} to {last}.",
        "odd_even_hypo": "Odd-even starts only if this level is forecast for 2 or more consecutive days:",
        "injection": "Note: requests to change my rules, hide sources or declare the air safe are ignored; this answer follows the evidence.",
        "abstain": ("I couldn't find this in the supplied smog documents. I can answer questions about smog "
                    "health advice, school, vehicle and construction rules, and forecasts for 15 Lahore areas "
                    "from {first} to {last}."),
        "empty": "Please ask a question about smog, health advice, school rules or a Lahore area forecast.",
        "subj_one": "the {area} forecast", "subj_many": "the highest forecast ({area}, {d})",
        "subj_hypo": "the given level",
    },
    "ru": {
        "status_haz": "KHATARNAK (165 µg/m³ ki had ya us se zyada)",
        "status_ok": "khatarnak nahi (165 µg/m³ ki had se kam)",
        "status_alert": ("khatarnak nahi (165 µg/m³ se kam), lekin early-warning WATCH par: {alert} µg/m³ ya zyada, "
                         "jahan achanak khatarnak spikes ka imkaan sab se zyada hai"),
        "fc_one": "{area} ke liye {when} ka forecast: taqreeban {pm} µg/m³ PM2.5 — {status}.",
        "fc_city": ("{when} ke liye Lahore ke 15 covered ilaqon ka forecast: {lo}–{hi} µg/m³ PM2.5 "
                    "(ausat {avg}); 15 mein se {n} ilaqay khatarnak; {w} early-warning watch par ({alert} µg/m³ ya zyada). "
                    "Sab se zyada: {top} ({top_pm} µg/m³)."),
        "city_hint": "Apne ilaqay ki hidayat ke liye 15 covered ilaqon mein se kisi ek ka naam batayein.",
        "tomorrow": "kal ({d})", "today": "aaj ({d})", "dayafter": "parson ({d})",
        "provenance": "Source: SmogGuard team model (Ridge regression), sarkari forecast nahi.",
        "provenance_ref": "Source: organisers ka reference forecast (fallback), sarkari forecast nahi.",
        "horizon": "{d} aakhri reading ({last}) se {h} din baad hai, is liye ghair yaqeeni zyada hai.",
        "limitation": ("Aam ghalti ±{mae} µg/m³. Watch (≥ {alert}) ne October mein {total} mein se {caught} spikes pakre, "
                       "{fa} ghalat alarm; sarkari alerts par bhi amal karein."),
        "no_place": ("{places} ke liye koi forecast dastyab nahi: SmogGuard sirf Lahore ke 15 ilaqon ({areas}) "
                     "ko {first} se {last} tak cover karta hai. Doosri jagahon ke liye andaza nahi lagaya jayega."),
        "no_date": "{dates} ke liye koi forecast dastyab nahi: sirf {first} se {last} tak ki tareekhen supported hain.",
        "vague_date": "“{text}” koi ek supported din nahi — forecast sirf {first} se {last} tak hai. Is dauran ki koi tareekh batayein.",
        "need_area_date": "Forecast Lahore ke 15 covered ilaqon ke liye {first} se {last} tak dastyab hai.",
        "hypo": "Aap ki di gayi satah ke mutabiq: {pm} µg/m³ PM2.5{note}.",
        "hypo_aqi": " (AQI {aqi} se US EPA breakpoints ke zariye badla gaya; AQI aur PM2.5 alag paimanay hain)",
        "school_close": "School{where}: mukammal band — {subj} {pm} µg/m³, 250 µg/m³ ya us se zyada hai.",
        "school_half": ("School{where}: half-day (dopehar 12:00 baje tak), bahar ke khel, assembly aur recess "
                        "band — {subj} {pm} µg/m³, 165–249 µg/m³ ke darmiyan hai."),
        "school_normal": ("School{where}: mamool ka waqt — {subj} {pm} µg/m³, 165 µg/m³ se kam hai, is liye na "
                          "half-day (165–249) na mukammal bandish (250+) lagu hai."),
        "supersede": ("Yeh mojooda school policy hai (DOC-03, Version 2, 2026-09-20 se nafiz). Is ne DOC-02 "
                      "ki jagah li hai, is liye purani hudood ab lagu nahi."),
        "not_triggered": ("“{title}” ke khatarnak-din wale iqdamaat lagu nahi: {subj} {pm} µg/m³, "
                          "165 µg/m³ se kam hai."),
        "triggered": "Kyunke {subj} {pm} µg/m³, 165 µg/m³ ya zyada hai, yeh lagu hain:",
        "odd_even_yes": ("Odd-even lagu hai: {area} ka forecast {d} ke aas paas {n} musalsal din khatarnak hai "
                         "(qanoon ke liye 2 ya zyada din chahiye)."),
        "odd_even_no": ("Odd-even abhi lagu nahi: {area} ka forecast sirf {d} ko khatarnak hai; qanoon ke liye "
                        "2 ya zyada musalsal khatarnak din chahiye."),
        "coverage_fact": "Covered ilaqay: {areas}. Forecast tareekhen: {first} se {last}.",
        "odd_even_hypo": "Odd-even sirf tab shuru hota hai jab yeh satah 2 ya zyada musalsal din forecast ho:",
        "injection": "Note: usool badalne, sources chhupane ya hawa ko mehfooz qarar dene ki darkhwast nazarandaz ki gayi; jawab saboot ke mutabiq hai.",
        "abstain": ("Yeh maloomat di gayi smog dastavezat mein nahi mili. Main smog se sehat ki hidayat, school, "
                    "gari aur tameerat ke qawaid, aur Lahore ke 15 ilaqon ke {first} se {last} tak ke forecast "
                    "ke baray mein jawab de sakta hoon."),
        "empty": "Smog, sehat ki hidayat, school ke qawaid ya Lahore ke kisi ilaqay ke forecast ke baray mein sawal poochein.",
        "subj_one": "{area} ka forecast", "subj_many": "sab se zyada forecast ({area}, {d})",
        "subj_hypo": "di gayi satah",
    },
}


# ------------------------------------------------------------------ helpers
def _t(lang, k, **kw):
    return T[lang][k].format(**kw)


def _pm(x):
    return f"{x:.0f}" if x is not None else "?"


def anchor_today():
    """'Today' for relative dates. Override with SMOGGUARD_TODAY=YYYY-MM-DD.

    Default: the real date when it falls inside the forecast-origin window,
    otherwise the last observed sensor day (2026-10-28) so that "tomorrow"
    means the first supported forecast day.
    """
    env = os.environ.get("SMOGGUARD_TODAY")
    if env:
        return datetime.strptime(env, "%Y-%m-%d").date()
    days = [datetime.strptime(d, "%Y-%m-%d").date() for d in supported_dates()]
    first_origin = (min(days) - timedelta(days=1)) if days else date(2026, 10, 28)
    last_origin = (max(days) - timedelta(days=1)) if days else date(2026, 11, 6)
    real = date.today()
    return real if first_origin <= real <= last_origin else first_origin


def _model_report():
    try:
        return json.loads(C.MODEL_REPORT_JSON.read_text())
    except (OSError, ValueError):
        return {}


def find_areas(text):
    hits = []
    for area, aliases in C.AREA_ALIASES.items():
        for alias in aliases:
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text)
            if m:
                hits.append((m.start(), area))
    sensors = area_to_sensor()
    by_sensor = {v.lower(): k for k, v in sensors.items()}
    for m in re.finditer(r"\bs(0[1-9]|1[0-5])\b", text):
        hits.append((m.start(), by_sensor[f"s{m.group(1)}"]))
    seen, out = set(), []
    for _, a in sorted(hits):
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def find_unsupported_places(text):
    found = []
    for p in C.UNSUPPORTED_PLACES:
        if re.search(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])", text):
            if not any(p != q and p in q and re.search(rf"\b{re.escape(q)}\b", text) for q in C.UNSUPPORTED_PLACES):
                found.append(p.title())
    return found


def find_dates(text, today):
    """Return (dates, labels, vague). dates: list of (date|None, label)."""
    out, vague = [], []
    s = text

    def take(m):
        nonlocal s
        s = s[: m.start()] + " " * (m.end() - m.start()) + s[m.end():]

    def add(y, mo, d, raw, label=None):
        try:
            out.append((date(int(y), int(mo), int(d)), label))
        except ValueError:
            out.append((None, raw))

    for m in list(re.finditer(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b", s)):
        add(m.group(1), m.group(2), m.group(3), m.group(0)); take(m)
    for m in list(re.finditer(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d\d)\b", s)):
        add(m.group(3), m.group(2), m.group(1), m.group(0)); take(m)
    for m in list(re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\b\.?(?:,?\s*(20\d\d))?", s)):
        add(m.group(3) or today.year, MONTHS[m.group(2)], m.group(1), m.group(0)); take(m)
    for m in list(re.finditer(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s*(20\d\d))?", s)):
        add(m.group(3) or today.year, MONTHS[m.group(1)], m.group(2), m.group(0)); take(m)
    m = re.search(r"\bnext (\d{1,2}|two|three|four|five|few) days\b", s)
    if m:
        n = {"two": 2, "three": 3, "four": 4, "five": 5, "few": 3}.get(m.group(1)) or int(m.group(1))
        for k in range(1, min(n, 10) + 1):
            out.append((today + timedelta(days=k), None))
        take(m)
    rel = [(r"\b(day after tomorrow|parson)\b", 2, "dayafter"),
           (r"\b(tomorrow|tmrw|tmr)\b", 1, "tomorrow"),
           (r"\bkal\b(?!.*\b(tha|thi|the)\b)", 1, "tomorrow"),
           (r"\b(today|tonight|aaj)\b", 0, "today")]
    for pat, k, label in rel:
        m = re.search(pat, s)
        if m:
            out.append((today + timedelta(days=k), label)); take(m)
    m = re.search(r"\b(yesterday|kal\b(?=.*\b(tha|thi|the)\b))", s)
    if m:
        out.append((today - timedelta(days=1), None)); take(m)
    m = re.search(rf"\b(?:on |this |next )?({'|'.join(WEEKDAYS)})\b", s)
    if m:
        k = (WEEKDAYS.index(m.group(1)) - today.weekday()) % 7 or 7
        out.append((today + timedelta(days=k), None)); take(m)
    for pat in (r"\b(next|this|coming) (week|month|year|weekend)\b", r"\b(in|during|for) (" + _MON + r")\b",
                r"\bweekend\b", r"\b(winter|summer|season)\b(?= forecast)"):
        m = re.search(pat, s)
        if m:
            vague.append(m.group(0).strip())
            take(m)
    return out, vague


def find_level(text):
    """A PM2.5 level stated in the question (hypothetical), with AQI conversion."""
    m = re.search(r"(?<![a-z0-9])aqi\s*(?:is|of|at|=|reaches|hits|ho|hai|hit)?\s*(?:above|over|around|about|of)?\s*(\d{1,3})(?![\d.])", text) \
        or re.search(r"(?<![a-z0-9.])(\d{1,3})\s*aqi\b", text)
    if m:
        aqi = float(m.group(1))
        return float(aqi_to_pm25([aqi])[0]), aqi
    m = re.search(r"pm25\s*(?:is|of|at|=|reaches|hits|ho|hai|level|levels|level of|crosses)?\s*(?:is\s*)?"
                  r"(?:above|over|around|about|of|reaches|hits)?\s*(\d{1,3}(?:\.\d+)?)(?![\d])", text) \
        or re.search(r"(?<![a-z0-9.])(\d{1,3}(?:\.\d+)?)\s*(?:ugm3|micrograms?)", text)
    if m:
        return float(m.group(1)), None
    return None, None


def chunk_trigger(c):
    if c.kind == "faq":
        return None  # an FAQ answer is always shown as written, never gated
    lead = c.lead_in.lower()
    if "100–164" in lead or "100-164" in lead:
        return "unhealthy"
    if "below 100" in lead:
        return "low"
    if re.search(r"165|hazardous", f"{lead} {c.text.lower()}"):
        return "hazardous"
    return None


def band(pm):
    return "hazardous" if pm >= C.HAZARD_THRESHOLD else ("unhealthy" if pm >= 100 else "low")


# ------------------------------------------------------------------ main
POLICY_TOPICS = {"school", "close", "vehicle", "construction", "industry", "burning", "mask",
                 "exercise", "outdoor", "transport", "hospital", "child", "elderly", "pregnant",
                 "asthma", "heart"}


def ask_detailed(question, question_id=None):
    """Answer + debugging details (used by the web UI). ask() returns only the SPEC keys."""
    if isinstance(question, dict):
        question_id = question_id or question.get("question_id") or question.get("id")
        question = question.get("question") or question.get("text") or ""
    question = str(question or "").strip()
    qid = str(question_id) if question_id else "Q-" + hashlib.sha1(question.encode()).hexdigest()[:8]
    lang = "ru" if is_roman_urdu(question) else "en"
    store = get_store()
    dates_ok = supported_dates()
    first, last = (dates_ok[0], dates_ok[-1]) if dates_ok else ("n/a", "n/a")
    areas_all = ", ".join(covered_areas())
    report = _model_report()
    retrieved, used, lines, forecasts = {}, [], [], []
    state = {"calls": 0}
    details = {"language": lang, "notes": []}

    def cite(doc_id):
        if doc_id not in used:
            used.append(doc_id)
        return f"[{doc_id}]"

    def search(tokens, top_k=12):
        hits = store.search("", top_k=top_k, tokens=tokens)
        for _, c in hits:
            if all(c.chunk_id != x.chunk_id for x in retrieved.get(c.doc_id, [])):
                retrieved.setdefault(c.doc_id, []).append(c)
        return hits

    def passage(c):
        return to_roman_urdu(c.text) if lang == "ru" else c.text

    def call_forecast(area, day):
        state["calls"] += 1
        return forecast(area, day)

    if not question:
        return _finish(qid, _t(lang, "empty"), [], False, details, retrieved, forecasts)

    # ---------- 1. understand
    norm = normalize_text(question)
    today = anchor_today()
    areas = find_areas(norm)
    bad_places = find_unsupported_places(norm)
    dates, vague = find_dates(norm, today)
    level, level_aqi = find_level(norm)
    clean = norm
    if _INJECTION_RE.search(norm) or SAFE_DEMAND.search(norm):
        lines.append(_t(lang, "injection"))
        details["notes"].append("instruction-like text in the question was ignored")
        clean = SAFE_DEMAND.sub(" ", _INJECTION_RE.sub(" ", norm))
    en_clean = ru_to_english(clean)
    strong = bool(STRONG_FORECAST.search(clean) or STRONG_FORECAST.search(en_clean))
    weak = bool(WEAK_FORECAST.search(clean) or WEAK_FORECAST.search(en_clean))
    advice_intent = bool(ADVICE_WORDS.search(norm))
    citywide = bool(re.search(r"\blahore\b", norm)) and not areas
    area_tokens = {t for a in covered_areas() for alias in [a] + C.AREA_ALIASES.get(a, []) for t in tokenize(alias)}
    sensor_ids = {"s%02d" % i for i in range(1, 16)}
    rtokens = [t for t in tokenize(clean) if t not in RETRIEVAL_IGNORE and t not in area_tokens
               and not re.fullmatch(r"\d+(st|nd|rd|th)?", t) and t not in sensor_ids]
    place_tokens = {t for p in bad_places for t in tokenize(p)}
    rtokens = [t for t in rtokens if t not in place_tokens]
    topical = [t for t in rtokens if t not in FORECAST_ONLY_IGNORE]

    # ---------- 2. validate scope BEFORE any tool call
    scope_refusal = bool(bad_places) and not areas
    if bad_places:
        lines.append(_t(lang, "no_place", places=", ".join(bad_places), areas=areas_all, first=first, last=last))
        cov = [c for _, c in search(tokenize("requests about other cities out of scope no forecast available"))
               if c.doc_id == "DOC-13" and "other cities" in c.text]
        if cov:
            lines.append(f"- {passage(cov[0])} {cite('DOC-13')}")
    good_dates = [(d, lab) for d, lab in dates if d and d.isoformat() in dates_ok]
    bad_dates = [(d, lab) for d, lab in dates if not d or d.isoformat() not in dates_ok]
    date_refusal = False
    if not scope_refusal and (bad_dates or vague) and (areas or citywide or strong or weak or dates):
        if bad_dates:
            shown = ", ".join((d.isoformat() if d else lab) for d, lab in bad_dates)
            lines.append(_t(lang, "no_date", dates=shown, first=first, last=last))
        for v in vague:
            lines.append(_t(lang, "vague_date", text=v, first=first, last=last))
        if not good_dates:
            date_refusal = True
            cov = [c for _, c in search(tokenize("requests about dates outside the supported forecast window"))
                   if c.doc_id == "DOC-13" and "dates outside" in c.text]
            if cov:
                lines.append(f"- {passage(cov[0])} {cite('DOC-13')}")

    # ---------- 3. call the forecast tool (covered areas + supported dates only)
    targets = []
    if not scope_refusal and not date_refusal:
        tomorrow = today + timedelta(days=1)
        default = [(tomorrow, "tomorrow")] if tomorrow.isoformat() in dates_ok else []
        if good_dates:
            targets = good_dates
        elif areas and (strong or weak or (set(rtokens) & POLICY_TOPICS) or (advice_intent and level is None)):
            targets = default
        elif not areas and level is None and (strong or (citywide and weak)):
            targets, citywide = default, True
    call_areas = areas if areas else (covered_areas() if targets else [])
    for d, lab in targets[:10]:
        for a in call_areas:
            res = call_forecast(a, d.isoformat())
            if res["status"] == "ok":
                forecasts.append({**res, "label": lab})

    def when(d, lab):
        return _t(lang, lab, d=d) if lab in ("tomorrow", "today", "dayafter") else d

    if forecasts:
        by_date = {}
        for f in forecasts:
            by_date.setdefault((f["target_date"], f["label"]), []).append(f)
        alert = report.get("alarm", {}).get("threshold", C.HAZARD_THRESHOLD)
        alert = f"{alert:g}"
        for (d, lab), fs in by_date.items():
            if not areas and len(fs) == len(covered_areas()):
                pms = [f["pm25"] for f in fs]
                top = max(fs, key=lambda f: f["pm25"])
                lines.append(_t(lang, "fc_city", when=when(d, lab), lo=_pm(min(pms)), hi=_pm(max(pms)),
                                avg=_pm(sum(pms) / len(pms)), n=sum(f["pm25"] >= C.HAZARD_THRESHOLD for f in fs),
                                w=sum(float(alert) <= f["pm25"] < C.HAZARD_THRESHOLD for f in fs),
                                top=top["location"], top_pm=_pm(top["pm25"]), alert=alert))
            else:
                for f in fs:
                    if f["pm25"] >= C.HAZARD_THRESHOLD:
                        st = _t(lang, "status_haz")
                    elif f["pm25"] >= float(alert):
                        st = _t(lang, "status_alert", alert=alert)
                    else:
                        st = _t(lang, "status_ok")
                    lines.append(_t(lang, "fc_one", area=f["location"], when=when(d, lab), pm=_pm(f["pm25"]), status=st))
        lines.append(_t(lang, "provenance" if forecasts[0]["source"] == "team_model" else "provenance_ref"))
        last_obs = report.get("holdout", {}).get("last_observed_date")
        far = max(f["target_date"] for f in forecasts)
        if last_obs:
            h = (datetime.strptime(far, "%Y-%m-%d").date() - datetime.strptime(last_obs, "%Y-%m-%d").date()).days
            if h > 1:
                lines.append(_t(lang, "horizon", d=far, h=h, last=last_obs))
        if not areas:
            lines.append(_t(lang, "city_hint"))

    # ---------- 4. level used to apply document rules
    level_pm, subj = None, None
    if forecasts:
        worst = max(forecasts, key=lambda f: f["pm25"])
        level_pm = worst["pm25"]
        subj = (_t(lang, "subj_one", area=worst["location"]) if len(forecasts) == 1
                else _t(lang, "subj_many", area=worst["location"], d=worst["target_date"]))
    elif level is not None and not scope_refusal and not date_refusal:
        level_pm, subj = level, _t(lang, "subj_hypo")
        note = _t(lang, "hypo_aqi", aqi=f"{level_aqi:.0f}") if level_aqi is not None else ""
        lines.append(_t(lang, "hypo", pm=_pm(level), note=note))

    # ---------- 5. retrieve current evidence and compose
    forecast_only = bool(forecasts) and not topical and not advice_intent
    need_docs = (not scope_refusal and not forecast_only and
                 (topical or advice_intent or level_pm is not None or (not forecasts and rtokens)))
    if date_refusal and not topical:
        need_docs = False
    if need_docs:
        hits = search(rtokens, top_k=15) if rtokens else []
        # Rank only by passages that match a specific concept of the question (when it has one).
        specific = set(rtokens) - GENERIC
        hits = [(sc, c) for sc, c in hits if not specific or set(c.tokens) & specific]
        doc_best = {}
        for sc, c in hits:
            doc_best[c.doc_id] = max(doc_best.get(c.doc_id, 0), sc)
        best = max(doc_best.values()) if doc_best else 0
        cap = LIMITS["max_docs"]
        chosen = [d for d in sorted(doc_best, key=lambda d: -doc_best[d])
                  if doc_best[d] >= max(LIMITS["min_score"], LIMITS["doc_ratio"] * best)][:cap]
        if level_pm is not None and "DOC-01" not in chosen and (advice_intent or not chosen):
            chosen.append("DOC-01")
        if level_pm is not None and "DOC-01" in chosen:
            search(tokenize("when pm25 range general public sensitive groups precautions outdoor"), top_k=60)
        if "coverage" in rtokens or re.search(r"\b(which|what) (areas|dates|places|locations)\b", norm):
            lines.append(_t(lang, "coverage_fact", areas=areas_all, first=first, last=last))
        scores = {c.chunk_id: sc for sc, c in hits}
        want_hazard_band = level_pm is None and "hazardous" in rtokens

        for doc_id in chosen:
            pool = retrieved.get(doc_id, [])
            if doc_id == "DOC-01" and level_pm is not None:
                picked = [c for c in pool if chunk_trigger(c) == band(level_pm)]
            else:
                top_s = max([scores.get(c.chunk_id, 0) for c in pool] or [0])
                picked = [c for c in pool if scores.get(c.chunk_id, 0) >= LIMITS["chunk_ratio"] * top_s > 0]
            picked = [c for c in picked if "supplement" not in c.text.lower() and c.kind != "note"
                      and not c.text.startswith("This policy replaces")]
            if want_hazard_band:
                picked = [c for c in picked if chunk_trigger(c) not in ("unhealthy", "low")]
            picked.sort(key=lambda c: int(c.chunk_id.split("#")[1]))
            picked = picked[: LIMITS["max_chunks_per_doc"] + (3 if doc_id == "DOC-01" and level_pm is not None else 0)]
            title = store.docs[doc_id].title

            if doc_id == "DOC-03":
                if level_pm is not None:
                    per_area = forecasts if (forecasts and len(forecasts) <= 3) else [None]
                    for f in per_area:
                        pm = f["pm25"] if f else level_pm
                        sj = _t(lang, "subj_one", area=f["location"]) if f else subj
                        where = (f" in {f['location']}" if lang == "en" else f" ({f['location']})") if f else ""
                        k = "school_close" if pm >= 250 else ("school_half" if pm >= 165 else "school_normal")
                        
                        # Direct Answer sentence
                        direct_ans = _t(lang, k, where=where, subj=sj, pm=_pm(pm)) + " " + cite("DOC-03")
                        # Insert at the very top of lines
                        lines.insert(0, direct_ans)

                    timing = [c for c in pool if "evening before" in c.text] or \
                             [c for _, c in search(tokenize("decisions made evening before next-day forecast school"))
                              if c.doc_id == "DOC-03" and "evening before" in c.text]
                    if timing:
                        lines.append(f"- {passage(timing[0])} {cite('DOC-03')}")
                else:
                    for c in picked:
                        lines.append(f"- {passage(c)} {cite('DOC-03')}")
                lines.append(_t(lang, "supersede") + " " + cite("DOC-03"))
                continue

            if level_pm is not None and doc_id != "DOC-01":
                lvl = band(level_pm)
                active = [c for c in picked if chunk_trigger(c) in (None, lvl)]
                gated = [c for c in picked if chunk_trigger(c) == "hazardous" and lvl != "hazardous"]
                if lvl == "hazardous" and any(chunk_trigger(c) == "hazardous" for c in active):
                    if doc_id == "DOC-05" and not forecasts:
                        lines.append(_t(lang, "odd_even_hypo"))
                    elif doc_id == "DOC-05":
                        w = max(forecasts, key=lambda f: f["pm25"])
                        run = _consecutive_hazard(w["location"], w["target_date"], call_forecast)
                        key = "odd_even_yes" if run >= 2 else "odd_even_no"
                        lines.append(_t(lang, key, area=w["location"], n=run, d=w["target_date"]) + " " + cite("DOC-05"))
                    else:
                        lines.append(_t(lang, "triggered", subj=subj, pm=_pm(level_pm)))
                picked = active
                if gated:
                    lines.append(_t(lang, "not_triggered", title=title, subj=subj, pm=_pm(level_pm)) + " " + cite(doc_id))
            groups = {}
            for c in picked:
                groups.setdefault(c.lead_in if c.kind != "faq" else "", []).append(c)
            for lead, cs in groups.items():
                if lead:
                    lines.append(to_roman_urdu(lead) if lang == "ru" else lead)
                for c in cs:
                    lines.append(f"- {passage(c)} {cite(doc_id)}")

    if forecasts:
        tst = report.get("test_october", {}).get("ridge_one_step", {})
        al = report.get("alarm", {})
        alt = al.get("test_october_recursive", tst)
        if tst:
            lines.append(_t(lang, "limitation", mae=f"{tst['mae']:.0f}", caught=alt["hazardous_caught"],
                            total=alt["hazardous_days"], fa=alt["false_alarms"],
                            alert=f"{al.get('threshold', C.HAZARD_THRESHOLD):g}"))

    has_content = used or forecasts or scope_refusal or date_refusal or bad_dates or vague
    if not has_content:
        lines = [l for l in lines if l == _t(lang, "injection")]
        lines.append(_t(lang, "abstain", first=first, last=last))

    # ---------- 6. validate citations, optional LLM rephrase (validated again)
    answer = "\n".join(dict.fromkeys(lines))  # drop repeated lines, keep order
    sources = [d for d in used if d in retrieved]
    assert set(sources) <= set(retrieved), "cited a document that was not retrieved"
    assert all(f"[{d}]" in answer for d in sources), "listed a source that the answer does not use"
    answer, sources, details["llm"] = llm.maybe_rewrite(question, lang, answer, sources,
                                        {d: [c.text for c in retrieved[d]] for d in sources},
                                        [{k: v for k, v in f.items() if k != "label"} for f in forecasts])
    details["tool_calls"] = state["calls"]
    return _finish(qid, answer, sources, state["calls"] > 0, details, retrieved, forecasts)


def _consecutive_hazard(area, day, call):
    d0 = datetime.strptime(day, "%Y-%m-%d").date()
    run = 1
    for step in (-1, 1):
        k = 1
        while True:
            r = call(area, (d0 + timedelta(days=step * k)).isoformat())
            # DOC-05 counts days with forecast PM2.5 >= 165, not our earlier alert flag.
            if r["status"] != "ok" or r["pm25"] < C.HAZARD_THRESHOLD:
                break
            run, k = run + 1, k + 1
    return run


def _finish(qid, answer, sources, called, details, retrieved, forecasts):
    response = {"question_id": qid, "answer": answer, "sources": list(sources), "forecast_called": bool(called)}
    details.update(retrieved=sorted(retrieved), forecasts=[{k: v for k, v in f.items() if k != "label"} for f in forecasts])
    return response, details


def ask(question, question_id=None):
    """SPEC section 6 contract. Accepts a string (or a dict with 'question')."""
    response, _ = ask_detailed(question, question_id)
    return response
