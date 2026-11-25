import re
import sys
import unicodedata
from collections import Counter
from token_counter import count_tokens

FILLER = {
    "i would like you to ": "",
    "could you please ": "",
    "can you please ": "",
    "go ahead and ": "",
    "in order to ": "to ",
    "due to the fact that ": "because ",
    "at this point in time": "now",
    "a large number of ": "many ",
    "it is important to note that ": "",
    "basically ": "",
    "actually ": "",
}

# verbs that start a request; "please" right before one of these is politeness
REQUEST_VERBS = {"write", "explain", "help", "make", "create", "give", "tell", "list", "fix", "generate",
                 "summarize", "summarise", "translate", "send", "check", "show", "find", "provide",
                 "describe", "analyze", "analyse", "convert", "rewrite", "do", "let", "use", "add",
                 "remove", "keep", "read", "answer", "reply", "share", "suggest", "review", "correct",
                 "improve", "update", "draft", "compare", "plan", "prepare", "calculate", "solve",
                 "build", "design", "go", "note", "include"}

# misspellings of "please" that are never real words, so they can go anywhere (lowercase only)
PLEASE_TYPOS = r"(?:p{2,}l+e+a+s+e+|p+l+e+a+s+e{2,}|pl[sz]*z[sz]*|pls{2,}|plez+|pleez+)"


def remove_please(text):
    """Remove "please" only where it is clearly politeness: at the start of a sentence
    or clause, or right before a request verb. Keep it when it is the topic or a verb
    ("people say please", "don't please everyone")."""
    text = re.sub(rf"\b{PLEASE_TYPOS}\b[ \t]*", "", text)

    # at the start of the text, a line, or a clause (after . ! ? , ; :)
    def at_start(m):
        if m.group("w").isupper() and m.group("w").lower() != "please":
            return m.group(0)                      # "PLS" is an acronym
        return m.group("lead")
    text = re.sub(r"(?P<lead>^|(?<=[.!?,;:])[ \t]+|(?<=\n))(?P<w>please|pls|plz)\b[.!,]?[ \t]*",
                  at_start, text, flags=re.IGNORECASE)

    # right before a request verb: "... and please write a poem"
    def before_verb(m):
        return "" if m.group(1).lower() in REQUEST_VERBS else m.group(0)
    return re.sub(r"(?<![\w'])please[ \t]+(?=([A-Za-z]+))", before_verb, text, flags=re.IGNORECASE)


def remove_filler(text):
    result = text
    for phrase, replacement in FILLER.items():
        # \b = whole words only, so a phrase can't match inside another word
        pattern = (r"\b" if phrase[0].isalnum() else "") + re.escape(phrase)
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    result = remove_please(result)
    # " for me" only right after a request verb ("summarize this article for me"),
    # never in "Is this plan right for me?"
    result = re.sub(r"\b((?:write|make|create|generate|find|summari[sz]e|draft|translate)\b[^.?!\n]{0,40}?)[ \t]+for me\b",
                    r"\1", result, flags=re.IGNORECASE)
    return result

# Only these words are collapsed when repeated ("the the", "hello hello").
# Other repeats may be intentional ("Bora Bora", "no no no", "knock knock").
REPEATABLE = {"the", "a", "an", "is", "to", "of", "in", "on", "and", "or", "for", "it", "i", "be",
              "are", "was", "that", "this", "with", "hello", "hi", "hey", "please", "thanks"}

def remove_repeated_words(text):
    # "hello hello" → "hello",  "the the" → "the"  (lowercase only, so names stay)
    def collapse(m):
        word = m.group(1)
        return word if word.islower() and word in REPEATABLE else m.group(0)
    return re.sub(r"\b(\w+)(?:[ \t]+\1\b)+", collapse, text)

def remove_decorations(text):
    # only a line made of one repeated character ("-----", "=====", "*****") is removed;
    # inline symbols like "***bold***", "===" or "!=" stay
    return re.sub(r"(?m)^[ \t]*([-=*_])\1{2,}[ \t]*$\n?", "", text)

def collapse_whitespace(text):
    text = re.sub(r"(?<=\S) {2,}", " ", text)   # runs of spaces inside a line → one space
    text = re.sub(r"\n{3,}", "\n\n", text)      # 3+ newlines → one blank line
    return text                                 # leading indentation and tabs are kept

# real words with repeated letters
STRETCH_OK = {"zzz", "zzzz", "sss", "brrr", "aaa", "aaaa", "www", "xxx", "mmm", "hmmm", "shhh",
              "grrr", "ahhh", "ooo", "eee", "iii", "vvv"}

def shrink_stretched_letters(text):
    # "appp" -> "app", "chaaaal" -> "chaal", "sureee" -> "suree" (the spell step fixes the rest)
    # skips hex values (#fff, 0xfff), whitelisted words, and words with digits or capitals
    def fix(m):
        word = m.group(0)
        if text[m.start() - 1:m.start()] == "#" or word.lower().startswith("0x"):
            return word
        if word.lower() in STRETCH_OK or any(c.isdigit() or c.isupper() for c in word):
            return word
        return re.sub(r"([a-vx-z])\1{2,}", r"\1\1", word)
    return re.sub(r"\b\w+\b", fix, text)

def remove_keyboard_spam(text):
    # button-mashing like "plslplsplsplsplpsl": lowercase, 6+ letters made only of p, l, s, z,
    # or one 2-3 letter chunk repeated 3+ times ("asdasdasd"). Capitals (PLS, LSP) are kept.
    text = re.sub(r"\b(?=[plsz]*p)(?=[plsz]*l)[plsz]{6,}\b[ \t]*", "", text)
    return re.sub(r"\b([a-z]{2,3})\1{2,}\b[ \t]*", "", text)

CODE_CHARS = set("<>{};/\\|")

def remove_symbol_junk(text):
    # 4+ mixed symbols like "???????_))(__)()(_(" -> "?"  (keeps one ? ! or . if the run started with it)
    # keeps markdown lines (# heading, | table |) and code-like runs (<!--, **/*.py, my_var____name)
    def clean_line(line):
        if line.lstrip().startswith(("#", "|")) or re.fullmatch(r"\s*([-=*_])\1{2,}\s*", line):
            return line                                     # markdown, or a divider line for remove_decorations
        def keep_first(m):
            run = m.group(0)
            left, right = line[m.start() - 1:m.start()], line[m.end():m.end() + 1]
            if CODE_CHARS & set(run):
                return run                                  # looks like code or markup
            if left.isalnum() and right.isalnum():
                return run                                  # inside a word
            return run[0] if run[0] in "?!." else " "
        return re.sub(r"(?:[^\w\s]|_){4,}", keep_first, line)
    return "\n".join(clean_line(l) for l in text.split("\n"))

def pre_clean(text):
    """Cheap fixes that help the spell step: stretched letters, spam, symbol junk.
    Quoted text and code stay protected."""
    original = text
    text, saved = protect(text)
    text = shrink_stretched_letters(text)
    text = remove_keyboard_spam(text)
    text = remove_symbol_junk(text)
    text = collapse_whitespace(text).strip()
    try:
        return restore(text, saved)
    except ValueError:
        return original                   # never lose protected text


ADDRESS_WORDS = r"(bhai|bro|sir|yaar|janab|there|team|all|everyone|baby|babe|babay|jaan|dost|friend)"

def remove_greeting(text):
    # removes greetings like "hello,", "hi bhai", "salam sir" only at the START, and only when
    # followed by punctuation, an address word, or small talk -- so "Hello World program"
    # and "Hey Jude lyrics" stay. Something must be left afterwards.
    cleaned = re.sub(
        r"^\s*(hello|hi|hey|dear|salam|salaam|assalam[u-]?\s?o?\s?alaikum|aoa)\b"
        r"(?:\s*[,!.]+|\s+((mere|meri|my|dear)\s+)?" + ADDRESS_WORDS + r"\b[,!.]?"
        r"|(?=\s+(how\s+(are|r)\s+(you|u)|kese|kaise|kesy|kya\s+haal)\b))\s*",
        "", text, flags=re.IGNORECASE)
    return cleaned if cleaned.strip() else text

def remove_pleasantries(text):
    # "I hope you are doing well today." adds tokens but nothing to the task
    return re.sub(r"\bI hope (you are|you're|u r) doing (well|good|fine)( today)?[.!]?\s*", "", text, flags=re.IGNORECASE)

def remove_small_talk(text):
    """Remove "how are you doing?" and "can you do that?" -- but only when
    something else is left, because sometimes "how are you" IS the question."""
    # only a full "how are you" sentence: followed by ? . ! , or the end of the text
    cleaned = re.sub(r"\bhow (are|r) (you|u)( doing| today)?\s*(?:[?.!,]+\s*|$)", "", text, flags=re.IGNORECASE)
    # Roman Urdu: "kese ho aap", "kya haal chaal hai apka"
    cleaned = re.sub(r"\b(kese|kaise|kesy|kaisay|kaisy|kesay|kesi|kaisi)\s+(ho|hain|hn|hai)(\s+(aap|ap|app|tum))?\s*[?.!]*\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bkya\s+haal(\s+chaal)?\s+(hai|he|h|hain)(\s+(apka|aapka|apkaa|tumhara))?\s*[?.!]*\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,]*\b(can|could|will) (you|u) (do|help with) (that|this|it)\s*[?.!]*\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned if len(cleaned.split()) >= 3 else text

def remove_closing_thanks(text):
    # removes "Thank you so much in advance for your help!" etc., but only at the END,
    # and not when thanks is part of the task ("ends with thank you", "a speech ... Thank you.")
    m = re.search(
        r"[\s,]*\b(thank you|thanks|thx|shukriya|shukria)( so much| very much| a lot)?( in advance)?( for (your|the) help)?[.!]*\s*$",
        text, flags=re.IGNORECASE)
    if not m:
        return text
    before = text[:m.start()]
    if re.search(r"\b(with|say|says|saying|ends?|ending|note|write)\W*$", before, re.IGNORECASE):
        return text
    if re.search(r"\b(thank|thanks|shukriya)\b", before, re.IGNORECASE):
        return text                                 # thanks is the topic of the prompt
    return before

def collapse_punctuation(text):
    text = re.sub(r"([?!])\1+", r"\1", text)                # ?? → ?   !!! → !   (never .. or ...)
    text = re.sub(r"[ \t]+([?!.,])(?=\s|$)", r"\1", text)   # "it ?" → "it?", but not ".NET" or "cd .."
    text = re.sub(r"([?!])[.?!]+", r"\1", text)             # "?." → "?"
    return text

def remove_duplicate_sentences(text):
    # removes a sentence only if it repeats exactly and has 5+ words;
    # keeps line breaks and never changes capitals
    parts = re.split(r"(?<=[.!?])([ \t]+|\n+)", text)       # sentences, with the gaps between them
    seen = set()
    out = []
    for i in range(0, len(parts), 2):
        sentence, gap = parts[i], (parts[i - 1] if i else "")
        key = re.sub(r"\s+", " ", sentence.strip().lower())
        if len(key.split()) >= 5 and key in seen:
            continue                                         # drop the repeat and its gap
        seen.add(key)
        out.append(gap + sentence)
    return "".join(out)



# Text inside quotes or code must never be changed (titles, code, exact data).
# A single quote only counts when it wraps something, not the apostrophe in don't / it's.
PROTECTED = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|(?<![\w'])'[^'\n]+'(?!\w)", re.DOTALL)


class Saved(list):
    """The protected parts, plus the placeholder marker used for them."""
    marker = "QXPH"


def protect(text):
    """Swap protected parts for placeholders the rules can't touch.
    The placeholder is made only of word characters (QXPH0QXPH), so no symbol rule
    can split it, and the marker changes if the text already contains it."""
    saved = Saved()
    marker = "QXPH"
    while marker in text:
        marker += "Q"
    saved.marker = marker
    def stash(match):
        saved.append(match.group(0))
        return f"{marker}{len(saved) - 1}{marker}"
    return PROTECTED.sub(stash, text), saved

def restore(text, saved):
    """Put the protected parts back. Raises ValueError if a placeholder was lost or
    duplicated, so callers fall back to the original text instead of failing silently."""
    marker = getattr(saved, "marker", "QXPH")
    pattern = re.compile(rf"{marker}(\d+){marker}")
    if sorted(int(i) for i in pattern.findall(text)) != list(range(len(saved))):
        raise ValueError("a protected part was lost or duplicated")
    return pattern.sub(lambda m: saved[int(m.group(1))], text)

def normalize_quotes(text):
    return text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

def protected_parts(text):
    return [m.group(0) for m in PROTECTED.finditer(text)]


STOPWORDS = {"the", "and", "that", "this", "with", "for", "from", "your", "what", "when",
             "which", "about", "into", "have", "will", "would", "should", "could", "there",
             "want", "like", "something", "because", "feeling", "come", "just", "please",
             "very", "really", "some", "also", "make", "sure", "thank", "thanks", "tell",
             "either", "answer", "must", "help", "them", "they", "then", "than", "been"}

NEGATIONS = r"(do not|don't|dont|does not|doesn't|must not|mustn't|should not|shouldn't|never|no|not|avoid|without|nahi|mat|نہیں|نہ|مت)"
# generic verbs after a negation; the real rule is in the noun that follows ("do not include EXAMPLES")
GENERIC_VERBS = {"include", "want", "need", "give", "mention", "write", "make", "add", "show",
                 "provide", "type", "put", "send", "share", "use", "more"}


def script_of(text):
    """Main writing system of a text: 'latin', 'arabic', 'cjk', 'devanagari', 'other' or 'none'."""
    counts = Counter()
    for ch in text:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            if name.startswith("LATIN"):
                counts["latin"] += 1
            elif name.startswith("ARABIC"):
                counts["arabic"] += 1
            elif name.startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL")):
                counts["cjk"] += 1
            elif name.startswith("DEVANAGARI"):
                counts["devanagari"] += 1
            else:
                counts["other"] += 1
    return counts.most_common(1)[0][0] if counts else "none"


def _words(text):
    """Words in any script (Unicode-aware), lowercased."""
    return re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower())


def _count_number(num, text):
    # whole numbers only: "5" does not match inside "500", "2" not inside "2024"
    return len(re.findall(rf"(?<![\d.,]){re.escape(num)}(?![.,]?\d)", text))


def _negated(word, words, window=4):
    """True if some occurrence of `word` has a negation within the 4 words before it."""
    for i, w in enumerate(words):
        if w.startswith(word[:5]):
            if re.search(rf"\b{NEGATIONS}\b", " ".join(words[max(0, i - window):i])):
                return True
    return False


def lost_constraints(before, after, check_subjects=True):
    """Rules and limits that disappeared between two versions of a prompt:
    every number must survive (as a whole number, as often as before), and every
    negative rule ("do not include examples") must keep its subject with a negation
    right before it."""
    lost = []
    low_after = after.lower()

    # 1. numbers: "500 words", "$899", "16GB" -- whole numbers, counted
    for num, n in Counter(re.findall(r"\d+(?:[.,]\d+)*", before)).items():
        if _count_number(num, after) < n:
            lost.append(num)

    # 2. negative rules
    if not check_subjects:
        # spell step: words may legitimately change (kode -> code), so only check
        # that no negation disappeared
        n_before = len(re.findall(rf"\b{NEGATIONS}\b", before.lower()))
        n_after = len(re.findall(rf"\b{NEGATIONS}\b", low_after))
        if n_after < n_before:
            lost.append(f"{n_before - n_after} negation(s)")
        return lost
    after_words = _words(after)
    for m in re.finditer(rf"\b{NEGATIONS}\b((?:\s+[\w']+){{1,4}})", before.lower()):
        words = [w for w in _words(m.group(2))
                 if len(w) > 3 and w not in STOPWORDS and w not in GENERIC_VERBS]
        if words and not _negated(words[0], after_words):   # words[0] = what the rule is about
            lost.append(f"{m.group(1)}{m.group(2)}".strip())
    return lost


def lost_requests(before, after):
    """Requests joined with "and / also / plus" ("a poem ... and also a haiku ... and a limerick"):
    the first content word after each one must survive."""
    lost = []
    after_words = _words(after)
    for m in re.finditer(r"\b(and|also|plus)\b((?:\s+[\w']+){1,4})", before.lower()):
        words = [w for w in _words(m.group(2))          # skip verbs: "and explain why..." asks nothing new
                 if len(w) > 3 and w not in STOPWORDS and w not in GENERIC_VERBS and w not in REQUEST_VERBS]
        if words and not any(a.startswith(words[0][:5]) for a in after_words):
            lost.append(words[0])
    return lost


def keyword_overlap(original, rewritten):
    """Share of the original's key words still in the rewrite (0.0 to 1.0).
    Words are compared by their first 5 letters, so 'lyrics' matches 'lyrical'.
    Works for any script; Chinese/Japanese/Korean are compared by character pairs."""
    def keys(t):
        if script_of(t) == "cjk":
            chars = [c for c in t if c.isalpha()]
            return {a + b for a, b in zip(chars, chars[1:])}
        min_len = 3 if script_of(t) in ("latin", "none") else 1
        return {w[:5] for w in _words(t)
                if len(w) > min_len and w not in STOPWORDS and w not in GENERIC_VERBS}
    orig = keys(original)
    if len(orig) < 4:
        return 1.0      # too few key words to judge (e.g. short, misspelled prompts)
    return len(orig & keys(rewritten)) / len(orig)


COMMAND_WORDS = {"npm", "pip", "git", "cd", "ls", "sudo", "py", "node", "yarn", "curl", "wget", "www"}

def capitalize_first(text):
    """Capitalize the first letter, but not words like iPhone, npm, e.g., paths or URLs."""
    first = text.split(None, 1)[0] if text.strip() else ""
    if (not first or any(c.isupper() for c in first[1:]) or re.search(r"[./\\:_\-@\d]", first)
            or first.lower() in COMMAND_WORDS):
        return text
    return text[:1].upper() + text[1:]


def optimize(text):
    original = text
    text, saved = protect(text)
    original_start = text.strip().split(None, 1)[:1]
    text = shrink_stretched_letters(text)
    text = remove_keyboard_spam(text)
    text = remove_symbol_junk(text)
    text = remove_repeated_words(text)
    text = remove_greeting(text)
    text = remove_closing_thanks(text)
    text = remove_pleasantries(text)
    text = remove_small_talk(text)
    text = remove_filler(text)
    text = remove_decorations(text)
    text = collapse_punctuation(text)
    text = collapse_whitespace(text)
    text = remove_duplicate_sentences(text)
    text = text.strip().rstrip(",;").strip()
    if text.split(None, 1)[:1] != original_start:
        text = capitalize_first(text)     # only when something was removed from the start
    try:
        return restore(text, saved)
    except ValueError:
        return original                   # never lose protected text

if __name__ == "__main__":
    prompt = input("Paste your prompt: ")

    if not prompt.strip():
        print("Empty prompt, nothing to optimize.")
        sys.exit()

    better = optimize(prompt)

    before = count_tokens(prompt)
    after = count_tokens(better)
    saved = before - after

    print("\nOriginal :", prompt)
    print("Optimized:", better)
    print(f"\nTokens: {before} → {after}  (saved {saved}, {saved / before:.0%})")
