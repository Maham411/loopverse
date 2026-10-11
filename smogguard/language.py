"""Text normalisation shared by retrieval and the assistant.

* English + Roman Urdu queries are mapped onto one vocabulary so BM25 can
  match Roman Urdu questions against the English documents.
* Common Urdu-script words (e.g. from browser speech recognition set to
  Urdu) are transliterated to Roman Urdu first.
"""
import re
import unicodedata

# ---------------------------------------------------------------- Urdu script
URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
URDU_PHRASES = {  # multi-word phrases first (replaced as whole phrases)
    "ڈی ایچ اے": "dha", "جوہر ٹاؤن": "johar town", "ماڈل ٹاؤن": "model town",
    "ٹھوکر نیاز بیگ": "thokar niaz baig", "علامہ اقبال ٹاؤن": "allama iqbal town",
    "فیصل ٹاؤن": "faisal town", "ٹاؤن شپ": "township", "اندرون شہر": "walled city",
    "رائیونڈ روڈ": "raiwind road", "بحریہ ٹاؤن": "bahria town", "ایئرپورٹ روڈ": "airport road",
    "ائیرپورٹ روڈ": "airport road", "اسلام آباد": "islamabad", "ایئر پیوریفائر": "air purifier",
}
URDU_WORDS = {
    "کل": "kal", "آج": "aaj", "ہوا": "hawa", "اسموگ": "smog", "سموگ": "smog", "اسکول": "school",
    "سکول": "school", "بند": "band", "بچوں": "bachon", "بچے": "bachay", "ماسک": "mask",
    "گلبرگ": "gulberg", "ڈیفنس": "defence", "واہگہ": "wagah", "شادمان": "shadman", "کینٹ": "cantt",
    "ٹاؤنشپ": "township", "لاہور": "lahore", "کراچی": "karachi", "پشاور": "peshawar", "کوئٹہ": "quetta",
    "ملتان": "multan", "کیا": "kya", "ہے": "hai", "ہیں": "hain", "ہوگی": "hogi", "ہوگا": "hoga",
    "کیسی": "kaisi", "کیسا": "kaisa", "کتنی": "kitni", "کتنا": "kitna", "آلودگی": "aloodgi",
    "صحت": "sehat", "بزرگ": "buzurg", "حاملہ": "hamla", "دمہ": "dama", "ہسپتال": "hospital",
    "گاڑی": "gari", "گاڑیاں": "gariyan", "باہر": "bahar", "اندر": "andar", "گھر": "ghar",
    "خطرناک": "khatarnak", "محفوظ": "mehfooz", "پیشگوئی": "forecast", "نومبر": "november",
    "اکتوبر": "october", "دسمبر": "december", "میں": "mein", "کا": "ka", "کی": "ki", "کے": "ke",
    "کو": "ko", "اور": "aur", "چاہیے": "chahiye", "کریں": "karein", "ورزش": "warzish",
    "کھڑکیاں": "khirkiyan", "احتیاط": "ehtiyat", "ہدایات": "hidayat", "تاریخ": "date",
}


def transliterate_urdu(text):
    if not re.search(r"[\u0600-\u06FF]", text):
        return text
    text = text.translate(URDU_DIGITS)
    for k in sorted(URDU_PHRASES, key=len, reverse=True):
        text = text.replace(k, f" {URDU_PHRASES[k]} ")
    words = re.split(r"(\s+|[؟?،,.!])", text)
    return "".join(URDU_WORDS.get(w, w) for w in words)


# ---------------------------------------------------------------- Roman Urdu
RU_PHRASES = {
    "school band": "school close", "schools band": "school close", "band ho": "close",
    "band honge": "close", "chahal qadmi": "walk", "saans lene": "breathing",
    "kya karna chahiye": "what should do advice", "kya karein": "what should do advice",
    "kya karen": "what should do advice", "air purifier": "purifier",
    "number plate": "vehicle", "odd even": "vehicle", "orange line": "transport",
}
RU_WORDS = {
    "kal": "tomorrow", "aaj": "today", "hawa": "air", "aloodgi": "pollution", "alodgi": "pollution",
    "aaloodgi": "pollution", "aludgi": "pollution", "dhuan": "smog", "dhuwan": "smog",
    "dhund": "smog", "sehat": "health", "khatarnak": "hazardous", "khatarnaak": "hazardous",
    "mehfooz": "safe", "mehfuz": "safe", "mahfooz": "safe", "bachay": "children",
    "bachon": "children", "bache": "children", "bachche": "children", "bacchon": "children",
    "bachchon": "children", "bachy": "children", "baccha": "children", "bacha": "children",
    "talaba": "students", "buzurg": "elderly", "bazurg": "elderly", "buzurgon": "elderly",
    "boorhay": "elderly", "budhe": "elderly", "hamla": "pregnant", "hamila": "pregnant",
    "dama": "asthma", "damma": "asthma", "mareez": "patients", "mareezon": "patients",
    "saans": "breathing", "sans": "breathing", "khansi": "cough", "khaansi": "cough",
    "seena": "chest", "seenay": "chest", "dil": "heart", "band": "close", "chutti": "close",
    "chhutti": "close", "gari": "vehicle", "gaari": "vehicle", "gaariyan": "vehicle",
    "gariyan": "vehicle", "gariyon": "vehicle", "gaadi": "vehicle", "gadi": "vehicle",
    "bahar": "outdoor", "baahar": "outdoor", "andar": "indoor", "ghar": "home",
    "khirki": "windows", "khirkiyan": "windows", "khirkiyon": "windows", "darwaza": "doors",
    "darwazay": "doors", "aspatal": "hospital", "haspatal": "hospital", "dawai": "medicine",
    "dawa": "medicine", "varzish": "exercise", "warzish": "exercise", "khel": "sports",
    "khelna": "sports", "sair": "walk", "bhatta": "brick", "bhattay": "brick", "bhatte": "brick",
    "tameer": "construction", "tameerat": "construction", "tamirat": "construction",
    "fasal": "crop", "fasl": "crop", "jalana": "burning", "jalane": "burning", "aag": "burning",
    "kachra": "waste", "kooda": "waste", "kiraya": "fare", "kiraye": "fare", "safar": "travel",
    "ehtiyat": "precautions", "ehtiyaat": "precautions", "ehtiyati": "precautions",
    "ehtiyaati": "precautions", "tadbeer": "precautions", "hidayat": "advice",
    "hidayaat": "advice", "mashwara": "advice", "mashwarah": "advice", "kitna": "level",
    "kitni": "level", "kitne": "level", "scool": "school", "iskool": "school", "sakool": "school",
    "qanoon": "rule", "qanun": "rule", "faisla": "decision", "paish": "forecast",
    "peshgoi": "forecast", "peshgoyi": "forecast", "parson": "dayafter",
}
# Words that are distinctly Roman Urdu (used only for language detection).
RU_MARKERS = {
    "kya", "hai", "hain", "kal", "aaj", "hoga", "hogi", "honge", "kaisa", "kaisi", "kaise",
    "kitna", "kitni", "mein", "chahiye", "karein", "karen", "karna", "nahi", "nahin", "liye",
    "bachon", "bachay", "bachche", "hawa", "aloodgi", "sehat", "khatarnak", "mehfooz", "ghar",
    "bahar", "kab", "kyun", "kyon", "mujhe", "humein", "apne", "apna", "wala", "wali", "waqt",
    "ka", "ki", "ke", "ko", "aur", "yeh", "ye", "woh", "agar", "toh", "tou", "bhi", "sakte",
    "sakta", "sakti", "jana", "jayen", "rahe", "rahi", "raha", "buzurg", "hamla", "dama",
    "gari", "band", "chutti", "theek", "zaroori", "kahan", "kaun", "kis", "konsa", "konsi",
    "dhuan", "warzish", "khirkiyan", "ehtiyat", "hidayat", "batain", "batayen", "bataen",
}

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do", "does", "did",
    "i", "me", "my", "we", "our", "you", "your", "it", "its", "this", "that", "these",
    "those", "of", "in", "on", "at", "to", "for", "from", "by", "with", "and", "or", "if",
    "what", "which", "who", "whom", "when", "where", "why", "how", "can", "could", "should",
    "would", "will", "shall", "may", "might", "must", "there", "their", "they", "them",
    "he", "she", "his", "her", "about", "as", "into", "than", "then", "so", "not", "no",
    "any", "all", "some", "much", "many", "more", "most", "very", "just", "also", "only",
    "please", "tell", "know", "need", "want", "get", "go", "going", "us", "s", "t",
    # Roman Urdu function words
    "kya", "hai", "hain", "ka", "ki", "ke", "ko", "mein", "aur", "se", "par", "pe", "ya",
    "hoga", "hogi", "honge", "kaisa", "kaisi", "kaise", "liye", "yeh", "ye", "woh", "agar",
    "toh", "tou", "bhi", "mujhe", "hum", "humein", "apne", "apna", "chahiye", "karna",
    "karein", "karen", "kab", "kyun", "kyon", "nahi", "nahin", "rahe", "rahi", "raha",
    "sakte", "sakta", "sakti", "batain", "batayen", "bataen", "wala", "wali", "kis", "kaun",
}

# Canonical concepts: every listed surface form maps to the first word.
SYNONYMS = {
    "child": ["kid", "kids", "child", "children", "student", "students", "pupil", "pupils",
              "son", "daughter", "baby", "babies", "infant", "toddler"],
    "school": ["school", "schools", "college", "class", "classes"],
    "close": ["close", "closes", "closed", "closing", "closure", "closures", "shut", "shutdown"],
    "mask": ["mask", "masks", "n95", "kn95", "respirator", "respirators"],
    "purifier": ["purifier", "purifiers", "hepa", "filter", "filters", "filtration"],
    "elderly": ["elderly", "older", "senior", "seniors", "aged", "grandparent", "grandparents",
                "grandmother", "grandfather", "65"],
    "pregnant": ["pregnant", "pregnancy", "expecting"],
    "asthma": ["asthma", "asthmatic", "copd", "inhaler", "inhalers", "lung", "lungs"],
    "heart": ["heart", "cardiac"],
    "vehicle": ["car", "cars", "vehicle", "vehicles", "drive", "driving", "plate", "plates",
                "odd", "even", "motorcycle", "motorbike", "bike", "private"],
    "transport": ["bus", "buses", "metro", "metrobus", "orange", "transport", "commute",
                  "commuting"],
    "construction": ["construction", "building", "demolition", "excavation", "site", "sites"],
    "industry": ["brick", "bricks", "kiln", "kilns", "industry", "industries", "factory",
                 "factories", "industrial", "stack"],
    "burning": ["burn", "burning", "burnt", "crop", "stubble", "residue", "waste", "garbage"],
    "hospital": ["hospital", "hospitals", "opd", "clinic", "nebulization", "nebulisation",
                 "nebulizer", "nebuliser"],
    "medical": ["doctor", "doctors", "medical", "emergency", "medicine", "medication",
                "pediatrician", "physician", "healthcare"],
    "exercise": ["exercise", "exercising", "jog", "jogging", "running", "workout",
                 "sport", "sports", "play", "playing", "walk", "walking", "cycling", "cricket",
                 "football", "strenuous", "exertion"],
    "outdoor": ["outdoor", "outdoors", "outside"],
    "indoor": ["indoor", "indoors", "inside", "home", "house", "room", "rooms", "bedroom",
               "bedrooms"],
    "window": ["window", "windows", "door", "doors"],
    "symptom": ["symptom", "symptoms", "cough", "coughing", "wheeze", "wheezing", "breath",
                "breathing", "chest", "shortness", "fatigue", "lips"],
    "pm25": ["pm25", "particle", "particles", "particulate"],
    "aqi": ["aqi", "index"],
    "sensor": ["sensor", "sensors", "network", "networks", "station", "stations",
               "monitor", "monitors", "monitoring", "reading", "readings"],
    "coverage": ["cover", "covered", "coverage", "covers", "scope", "supported"],
    "tip": ["tip", "tips", "remedy", "remedies", "plant", "plants", "community", "neighbor",
            "neighbors", "neighbour", "neighbours", "carpool"],
    "alert": ["alert", "alerts", "warning", "warnings"],
    "advice": ["advisory", "advice", "guidance", "precaution", "precautions",
               "recommendation", "recommendations", "recommended", "protect", "protection"],
    "fare": ["fare", "fares", "ticket", "tickets"],
    "forecast": ["forecast", "forecasts", "forecasted", "predict", "predicted", "prediction",
                 "predictions"],
    "hazardous": ["hazardous", "hazard", "dangerous", "danger", "severe"],
    "rule": ["rule", "rules", "policy", "policies", "regulation", "regulations", "directive",
             "law", "laws"],
}
_CANON = {form: canon for canon, forms in SYNONYMS.items() for form in forms}


def normalize_text(text):
    """Lower-case, transliterate Urdu script, unify PM2.5 / ug spellings."""
    text = unicodedata.normalize("NFKC", transliterate_urdu(str(text))).lower()
    text = re.sub(r"pm\s*2[.,]?\s*5", " pm25 ", text)
    text = re.sub(r"[µμ]g\s*/?\s*m\s*[³3]|ug\s*/\s*m\s*[³3]", " ugm3 ", text)
    text = text.replace("’", "'").replace("–", "-").replace("—", " - ")
    return text


def ru_to_english(text):
    """Map Roman Urdu phrases/words to English equivalents (for retrieval only)."""
    for k in sorted(RU_PHRASES, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(k)}\b", RU_PHRASES[k], text)
    return " ".join(RU_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", text))


def tokenize(text, expand_roman_urdu=True):
    """Tokens for BM25: normalised, Roman Urdu mapped, stopwords removed, canonicalised."""
    text = normalize_text(text)
    if expand_roman_urdu:
        text = ru_to_english(text)
    out = []
    for w in re.findall(r"[a-z0-9]+", text):
        if w in STOPWORDS or len(w) < 2 and not w.isdigit():
            continue
        if w not in _CANON and len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif w not in _CANON and len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(_CANON.get(w, w))
    return out


def is_roman_urdu(text):
    if re.search(r"[\u0600-\u06FF]", str(text)):
        return True
    words = set(re.findall(r"[a-z]+", normalize_text(text)))
    strong = {"kya", "hai", "hain", "hoga", "hogi", "kaisi", "kaisa", "chahiye", "mein",
              "kal", "aaj", "nahi", "nahin", "karein", "kitni", "kitna", "liye", "bachon",
              "hawa", "aloodgi", "sehat", "khatarnak", "mehfooz", "batain", "batayen"}
    return len(words & RU_MARKERS) >= 2 and len(words & strong) >= 1
