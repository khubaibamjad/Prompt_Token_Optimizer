import re
import json
import time
import hashlib
import threading
from pathlib import Path
import ollama
from token_counter import count_tokens
from optimizer import protect

MODEL = "gemma3:4b"          # used to compress the prompt
SPELL_MODEL = "gemma3:1b"    # smaller, faster model for the easy spelling task
                             # (falls back to MODEL if it isn't downloaded: ollama pull gemma3:1b)

# a client with a timeout, so the program can never hang forever
client = ollama.Client(timeout=120)

# prompts longer than this skip the AI steps instead of being cut short
MAX_AI_TOKENS = 1500


class OutputCutOff(Exception):
    """The model stopped before finishing its answer (output limit reached)."""


# ---------- Step 1: spelling ----------
SPELL_SYSTEM = """You fix spelling in prompts. Change NOTHING else.
- Fix typos (doig -> doing, revrsal -> reversal, hlp -> help).
- Fix the wrong word when context makes it clear (rite method -> write method).
- Expand texting short forms (r -> are, u -> you, dat -> that, ur -> your, ary -> array).
- Keep every word, greeting, question and punctuation mark otherwise. Do not shorten.
- Roman Urdu: fix its typos too (leik do -> likh do, live -> liye, krta -> karta, app -> aap), but NEVER translate it to English.
- Keep text inside quotes or code exactly as written.
- Do NOT answer the prompt.
- Put the corrected prompt between <prompt> and </prompt>. Write nothing else.

Example:
Original: hi how r u doig? can u hlp me rite a leter to my boss
Output: <prompt>hi how are you doing? can you help me write a letter to my boss</prompt>

Original: bhai mere live aik msg leik do ke mein kal nai aa skta
Output: <prompt>bhai mere liye aik msg likh do ke main kal nahi aa sakta</prompt>"""


# ---------- Step 3: compression ----------
COMPRESS_SYSTEM = """You compress prompts to the fewest tokens that still say everything the original says.
Write in a terse note style: drop "I want", "should be able to", "there should be", filler words and
most articles; use colons, commas and short phrases instead of full sentences.
- Keep every request and question. Never drop one.
- Keep names, numbers, limits and constraints ("500 words", "under 80 words").
- Keep EVERY "do not / don't / no / never / avoid" rule. If there are two, keep both.
- NEVER add a rule, restriction or "no ..." that the original does not have.
- Keep the intent: the order of steps (first, before, then) and plans (later, for now, eventually).
- Keep text inside quotes or code exactly as written.
- Keep the same language. Roman Urdu stays Roman Urdu. Never translate.
- Do NOT answer or carry out the prompt. Only rewrite it.
- Put the rewritten prompt between <prompt> and </prompt>. Write nothing else.

Examples:
Original: Help me to write method for array reversal?
Output: <prompt>Write a method to reverse an array.</prompt>

Original: Do not use any examples. Explain what an API is, and I don't want any code either.
Output: <prompt>Explain what an API is. No examples, no code.</prompt>

Original: I want sellers to upload products with images and prices, and customers should be able to search products and place orders.
Output: <prompt>Sellers: upload products (images, prices). Customers: search, order.</prompt>

Original: I might add payment integration later, so for now just implement a basic payment simulation. Before coding, figure out the architecture and explain how everything will work.
Output: <prompt>Payments: basic simulation for now, real integration later. First design the architecture and explain how it works, then code.</prompt>"""


def clean(text):
    """Pull the rewritten prompt out of the model's reply."""
    text = text.strip()

    # 1. best case: the model used the <prompt> tags
    match = re.search(r"<prompt>(.*?)(</prompt>|$)", text, flags=re.S | re.I)
    if match:
        text = match.group(1).strip()
    else:
        # 2. fallback: remove a chatty opener that ends in ":" at the start, like
        #    "Sure! Here is the optimized prompt:" or "**Rewritten prompt:**". Keep all paragraphs.
        text = re.sub(
            r"^[\s*#]*(?:(?:sure|okay|ok|certainly|of course|absolutely)\b[!.,]?\s*)?"
            r"(?:here(?:'s| is| are)\b[^:\n]{0,60}|(?:the\s+)?(?:optimi[sz]ed|rewritten|compressed|corrected|shortened|fixed)"
            r"(?:\s+(?:prompt|version|text))?|output)\s*:[\s*]*",
            "", text, flags=re.I)

    # 3. curly quotes -> straight quotes, so protected text still matches
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # 4. remove quotes around the WHOLE prompt only, never a title's own quotes
    if len(text) > 1 and text[0] == text[-1] == '"' and text.count('"') == 2:
        text = text[1:-1].strip()
    return text


# ---------- cache: the same prompt always gives the same answer (temperature 0) ----------
CACHE_FILE = Path(__file__).with_name("llm_cache.json")
try:
    CACHE = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    CACHE = {}

def cache_key(model, system, prompt):
    # the instructions are part of the key, so changing them never returns stale answers
    return hashlib.sha256(f"{model}|{system}|{prompt}".encode("utf-8")).hexdigest()

_CACHE_LOCK = threading.Lock()      # chunks may be processed in parallel

def save_cache():
    with _CACHE_LOCK:
        CACHE_FILE.write_text(json.dumps(CACHE, ensure_ascii=False, indent=1), encoding="utf-8")


def remember(system, model, prompt, reply):
    """Cache an answer. Called only after it passed the safety checks."""
    CACHE[cache_key(model, system, prompt)] = reply
    save_cache()

def forget(system, model, prompt):
    """Drop a cached answer that failed the safety checks, so it's retried next time."""
    if CACHE.pop(cache_key(model, system, prompt), None) is not None:
        save_cache()


def generation_options(system, prompt):
    """Output and context limits sized to the prompt, so nothing gets cut off."""
    num_predict = count_tokens(prompt) * 2 + 50
    needed = count_tokens(system) + count_tokens(prompt) + num_predict + 100
    num_ctx = max(2048, -(-needed // 1024) * 1024)          # round up to a multiple of 1024
    return {"temperature": 0, "num_predict": num_predict, "num_ctx": num_ctx}


def _field(response, key):
    value = getattr(response, key, None)
    if value is None and isinstance(response, dict):
        value = response.get(key)
    return value


def ask(system, prompt, model, note=""):
    """Send one prompt to the local model and return (cleaned reply, seconds).
    Uses the cache when the same prompt was accepted before (seconds = 0).
    `note` is extra feedback for a retry ("you dropped: desktop").
    Raises OutputCutOff if the model ran out of room before finishing."""
    key = cache_key(model, system, prompt + note)
    if key in CACHE:
        return CACHE[key], 0.0

    start = time.perf_counter()
    try:
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Original: {prompt}\n{note}Output:"},
            ],
            options=generation_options(system, prompt),   # temperature 0, sized limits
            keep_alive="30m",         # keep the model loaded for 30 minutes
        )
    except ollama.ResponseError as e:
        # model not downloaded? use the main model instead
        if e.status_code == 404 and model != MODEL:
            print(f"  (model '{model}' not found, using '{MODEL}'. Run: ollama pull {model})")
            return ask(system, prompt, MODEL, note)
        raise
    seconds = time.perf_counter() - start

    raw = response["message"]["content"]
    if _field(response, "done_reason") == "length" or (
            re.search(r"<prompt>", raw, re.I) and not re.search(r"</prompt>", raw, re.I)):
        raise OutputCutOff("the model's output was cut off before it finished")
    return clean(raw), seconds


# ---------- does the prompt even need a spell fix? ----------
# texting short forms and real-but-usually-wrong words a dictionary can't catch
SLANG = {"u", "r", "ur", "ya", "dat", "da", "dis", "plz", "pls", "thx", "luv", "hlp", "wat", "wht",
         "wid", "coz", "cuz", "bcoz", "b4", "gr8", "n", "msg", "rite", "nd", "im", "dont", "cant", "wont"}
TECH_WORDS = ["json", "api", "apis", "gpt", "llm", "ai", "tiktoken", "ollama", "python", "javascript", "sql",
              "html", "css", "url", "regex", "github", "git", "chatgpt", "claude", "gemma", "app",
              # common tech terms the dictionary doesn't know (so they aren't treated as typos)
              "frontend", "backend", "fullstack", "devops", "dto", "dtos", "jwt", "bcrypt", "postgresql",
              "postgres", "mysql", "mongodb", "typescript", "nodejs", "reactjs", "springboot", "docker",
              "kubernetes", "microservice", "microservices", "middleware", "async", "yaml", "config",
              "repo", "localhost", "signup", "login", "logout", "dataset", "datasets", "chatbot",
              "webhook", "webhooks", "schema", "env", "npm", "pip", "cli", "ui", "ux", "sdk", "oauth",
              "crud", "orm", "graphql", "redis", "nginx", "linux", "ci", "cd", "codebase", "refactor",
              "refactoring", "scalable", "maintainable", "responsive", "frontends", "backends",
              "admin", "admins", "dashboard", "ecommerce", "checkout", "signin", "username", "usernames",
              "auth", "db", "utils", "util", "params", "args", "async", "boolean", "enum", "enums", "json",
              "endpoint", "endpoints", "timestamp", "timestamps", "metadata", "plugin", "plugins", "toolbar"]

try:
    from spellchecker import SpellChecker
    SPELLER = SpellChecker()
    SPELLER.word_frequency.load_words(TECH_WORDS)
except ImportError:
    SPELLER = None    # not installed: py -m pip install pyspellchecker


def needs_spell_fix(text):
    """True if the prompt has likely typos or texting slang. Skipping the spell
    step for clean prompts saves one whole AI call."""
    if SPELLER is None:
        return True                                   # can't tell, so be safe
    text, _ = protect(text)                           # ignore quoted text and code
    words = []
    for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        w = m.group(0)
        # a capital at the start of a sentence isn't a name: "Halp me" -> "halp"
        if w[0].isupper() and w[1:].islower() and re.search(r"(^|[.!?])\s*$", text[:m.start()]):
            w = w.lower()
        words.append(w)
    words = [w for w in words if w.islower()]         # skip names and acronyms (Ali, GPT)
    if any(w in SLANG for w in words):
        return True
    unknown = SPELLER.unknown([w.strip("'") for w in words if len(w) > 1])
    # a long word that is just another form of a known word ("overcomplicate" vs
    # "overcomplicated") is a real word missing from the dictionary, not a typo
    typos = [w for w in unknown
             if not (len(w) >= 7 and any(c.startswith(w) or w.startswith(c)
                                         for c in (SPELLER.candidates(w) or [])))]
    return bool(typos)


def spell_fix(prompt, model=None):
    return ask(SPELL_SYSTEM, prompt, model or SPELL_MODEL)

def remember_spell(prompt, reply, model=None):
    remember(SPELL_SYSTEM, model or SPELL_MODEL, prompt, reply)

def forget_spell(prompt, model=None):
    forget(SPELL_SYSTEM, model or SPELL_MODEL, prompt)


def llm_optimize(prompt, feedback=""):
    """Compress a prompt. `feedback` explains why the previous try was rejected."""
    note = (f"Your previous rewrite was rejected because it {feedback}. "
            f"Rewrite again and keep every requirement.\n") if feedback else ""
    return ask(COMPRESS_SYSTEM, prompt, MODEL, note)

def remember_compression(prompt, reply):
    remember(COMPRESS_SYSTEM, MODEL, prompt, reply)

def forget_compression(prompt):
    forget(COMPRESS_SYSTEM, MODEL, prompt)


if __name__ == "__main__":
    prompt = input("Paste your prompt: ")
    fixed, t1 = spell_fix(prompt)
    print(f"Spell fixed ({t1:.1f}s): {fixed}")
    short, t2 = llm_optimize(fixed)
    print(f"Compressed  ({t2:.1f}s): {short}")
