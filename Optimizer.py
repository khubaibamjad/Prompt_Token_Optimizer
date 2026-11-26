import re
import sys
import unicodedata
from collections import Counter
from token_counter import count_tokens

FILLER = {
    "i would like you to ": "",
    "i want you to ": "",
    "i need you to ": "",
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
    "obviously ": "",
    " without any problems": "",
    " without any issues": "",
    " without any hassle": "",
}

SENTENCE_START = "\x00"      # temporary mark: "capitalize the next word"

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
        nxt = m.group("next") or ""
        # at a sentence start (not after , ; :) the next word now starts the sentence
        if re.search(r"(^|[.!?\n])[ \t]*$", text[:m.start("w")]):
            nxt = capitalize_first(nxt)
        return m.group("lead") + nxt
    text = re.sub(r"(?P<lead>^|(?<=[.!?,;:])[ \t]+|(?<=\n))(?P<w>please|pls|plz)\b[.!,]?[ \t]*(?P<next>\S+)?",
                  at_start, text, flags=re.IGNORECASE)

    # lowercase "pls" / "plz" in the middle of a sentence is politeness too, except when it's
    # a name ("the pls tool", "pls command") or an item in a list ("lsp and pls and spl")
    def mid_sentence(m):
        before = text[:m.start()].split()[-1:] or [""]
        after = text[m.end():].split()[:1] or [""]
        b, a = before[0].lower().strip(",;"), after[0].lower().strip(",;.!?")
        if b in {"the", "a", "an"} or a in {"tool", "command", "file", "package", "regression", "method"}:
            return m.group(0)
        if b in {"and", "or"} and a in {"and", "or"}:
            return m.group(0)
        return ""
    text = re.sub(r"(?<![\w'])(?:pls|plz)\b[ \t]*", mid_sentence, text)

    # right before a request verb: "... and please write a poem"
    def before_verb(m):
        return "" if m.group(1).lower() in REQUEST_VERBS else m.group(0)
    return re.sub(r"(?<![\w'])please[ \t]+(?=([A-Za-z]+))", before_verb, text, flags=re.IGNORECASE)


def remove_filler(text):
    result = text
    for phrase, replacement in FILLER.items():
        # \b = whole words only, so a phrase can't match inside another word
        pattern = (r"\b" if phrase[0].isalnum() else "") + re.escape(phrase)
        def replace(m, replacement=replacement):
            # removed at the start of a sentence: the next word now starts it ("The module ...")
            at_start = re.search(r"(^|[.!?]\s+|\n)\x00?$", result[:m.start()]) is not None
            if at_start and phrase[0].isalnum():
                return SENTENCE_START + replacement
            return replacement
        result = re.sub(pattern, replace, result, flags=re.IGNORECASE)
    result = remove_please(result)
    # "some kind of admin panel" -> "an admin panel"
    result = re.sub(r"\b([Ss])ome (?:kind|sort) of (?=(\w))",
                    lambda m: ("A" if m.group(1) == "S" else "a") + ("n " if m.group(2).lower() in "aeiou" else " "),
                    result)
    # "make sure (that) X" -> "ensure X", keeping a capital at the start of a sentence
    result = re.sub(r"\b([Mm])ake sure(?: that)?\b",
                    lambda m: "Ensure" if m.group(1) == "M" else "ensure", result)
    # capitalize the words that now start a sentence, then drop the marks
    result = re.sub(SENTENCE_START + r"+(\S+)", lambda m: capitalize_first(m.group(1)), result)
    result = result.replace(SENTENCE_START, "")
    # "(please) can you write ..." at the start of a sentence -> "write ..."; only before a request verb,
    # so a real question like "Can you swim?" stays
    def can_you(m):
        verb = m.group("verb")
        if verb.lower() not in REQUEST_VERBS:
            return m.group(0)
        sentence_start = re.search(r"(^|[.!?\n])\s*$", result[:m.start()])
        return m.group("lead") + (capitalize_first(verb) if sentence_start else verb)
    result = re.sub(r"(?P<lead>^|(?<=[.!?])[ \t]+|(?<=\n))(?:please\s+)?(?:can|could|would|will)\s+(?:you|u)\s+(?:please\s+)?(?P<verb>[A-Za-z]+)",
                    can_you, result, flags=re.IGNORECASE)
    # " for me" only right after a request verb ("summarize this article for me"),
    # never in "Is this plan right for me?"
    result = re.sub(r"\b((?:write|make|create|generate|find|summari[sz]e|draft|translate)\b[^.?!\n]{0,40}?)[ \t]+for me\b",
                    r"\1", result, flags=re.IGNORECASE)
    return result

# Only these words are collapsed when repeated ("the the", "hello hello").
# Other repeats may be intentional ("Bora Bora", "no no no", "knock knock").
REPEATABLE = {"the", "a", "an", "is", "to", "of", "in", "on", "and", "or", "for", "it", "i", "be",
              "are", "was", "that", "this", "with", "hello", "hi", "hey", "please", "thanks",
              "pls", "plz", "thx"}

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


ADDRESS_WORDS = r"(bhai|bro|sir|yaar|janab|there|team|all|everyone|baby|babe|babay|jaan|dost|friend|boy|boi|dude)"
# greetings, including common typos (helo, hallo, hii, heyy)
GREETING_WORDS = r"(hello|helo|hallo|hii+|hi|heyy*|dear|salam|salaam|assalam[u-]?\s?o?\s?alaikum|aoa)"

def remove_greeting(text):
    # removes greetings like "hello,", "hi bhai", "salam sir" only at the START, and only when
    # followed by punctuation, an address word, or small talk -- so "Hello World program"
    # and "Hey Jude lyrics" stay. Something must be left afterwards.
    # a run of greetings ("hi hello helo ...") is removed one by one
    cleaned = text
    for _ in range(5):
        step = re.sub(
            r"^\s*" + GREETING_WORDS + r"\b"
            r"(?:\s*[,!.]+|\s+((mere|meri|my|dear)\s+)?" + ADDRESS_WORDS + r"\b[,!.]?"
            r"|(?=\s+(how\s+((are|r)\s+)?(you|u)|kese|kaise|kesy|kya\s+haal)\b)"
            r"|(?=\s+" + GREETING_WORDS + r"\b))\s*",
            "", cleaned, flags=re.IGNORECASE)
        if step == cleaned:
            break
        cleaned = step
    return cleaned if cleaned.strip() else text

def remove_pleasantries(text):
    # "I hope you are doing well today." adds tokens but nothing to the task
    return re.sub(r"\bI hope (you are|you're|u r) doing (well|good|fine)( today)?[.!]?\s*", "", text, flags=re.IGNORECASE)

def remove_small_talk(text):
    """Remove "how are you doing?" and "can you do that?" -- but only when
    something else is left, because sometimes "how are you" IS the question."""
    # only a full "how are you" sentence: followed by ? . ! , or the end of the text
    # ...or followed by an address word: "how you doing boi, write ..."
    cleaned = re.sub(r"\bhow ((are|r) )?(you|u)( doing| today)?"
                     r"(?:\s*[?.!,]+\s*|\s+" + ADDRESS_WORDS + r"\b[?.!,]*\s*|\s*$)", "", text, flags=re.IGNORECASE)
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
             "either", "answer", "must", "help", "them", "they", "then", "than", "been", "between",
             # greetings and small talk carry no meaning for the task
             "hello", "helo", "hallo", "doing", "today", "well", "dude", "friend", "dost", "bhai",
             "yaar", "jaan", "baby", "babe", "dear",
             # generic verbs a terse rewrite often swaps ("figure out" -> "design", "implement" -> "")
             "might", "implement", "figure", "able", "allow", "allowed", "going"}

# words that are never the subject of a rule or request ("avoid USING jargon", "and WANTS protein")
NOT_SUBJECTS = {"want", "wants", "wanted", "need", "needs", "like", "sound", "seem", "look", "feel",
                "keep", "try", "eat", "use", "using", "make", "made", "does", "never", "avoid",
                "without", "nahi", "dont", "don't", "doesn't", "mustn't", "shouldn't",
                # vague nouns that just mean "the thing we're building"
                "system", "application", "platform", "everything", "something", "anything",
                "thing", "things", "stuff", "solution"}
# Roman Urdu function words: they carry no meaning and are often dropped in a good rewrite
ROMAN_URDU_FUNCTION = {"ek", "apne", "meri", "mera", "kyunke", "ke", "ko", "ka", "ki", "main", "hai", "do"}

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


def _stem(word):
    """Cut common endings: orders -> order, modifies -> modifi, modifying -> modify, lyrical -> lyric."""
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "al", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def _same_word(a, b):
    """Same word ignoring endings. Stems must share 5 letters ("overcomplicate" is NOT
    "oversimplification"); a short stem only needs to start the other (dict / dictionaries)."""
    a, b = _stem(a), _stem(b)
    short, long_ = sorted((a, b), key=len)
    if len(short) <= 4:
        return long_.startswith(short)
    return a[:5] == b[:5]


def _content_words(text, extra_skip=()):
    """Words in a short window that can be the subject: no stopwords, negations, helper verbs.
    Words ending in -ing are only used if there's nothing else ("avoid USING jargon" -> jargon)."""
    words = [w for w in _words(text)
             if len(w) > 3 and w not in STOPWORDS and w not in GENERIC_VERBS
             and w not in NOT_SUBJECTS and w not in ROMAN_URDU_FUNCTION and w not in extra_skip
             and not re.fullmatch(NEGATIONS, w)]
    plain = [w for w in words if not w.endswith("ing")]
    return plain or words


def _negated(word, words, window=4, allow_only=False):
    """True if some occurrence of `word` has a negation within the 4 words before it.
    With allow_only, "only" also counts ("not the orders of other sellers" = "only their own orders")."""
    marker = rf"\b({NEGATIONS[1:-1]}|only)\b" if allow_only else rf"\b{NEGATIONS}\b"
    for i, w in enumerate(words):
        if _same_word(w, word):
            if re.search(marker, " ".join(words[max(0, i - window):i])):
                return True
    return False


def split_chunks(text, max_tokens=60):
    """Split a long prompt into chunks of whole sentences, each about max_tokens long.
    Returns [(chunk, gap_after)], where "".join(chunk + gap) gives back the exact text.
    A chunk never crosses a line break, so paragraphs, list items, headings and tables keep
    their shape. Quoted text and code blocks are never split (protected while splitting)."""
    prot, saved = protect(text)
    marker = saved.marker
    raw = []
    lines = re.split(r"(\n+)", prot)                       # line, newlines, line, newlines, ...
    for i in range(0, len(lines), 2):
        line = lines[i]
        newlines = lines[i + 1] if i + 1 < len(lines) else ""
        pieces = re.split(r"(?<=[.!?])(\s+)", line)       # sentence, gap, sentence, gap, ...
        line_chunks, body = [], ""
        for j in range(0, len(pieces), 2):
            sentence = pieces[j]
            gap = pieces[j + 1] if j + 1 < len(pieces) else ""
            if body.strip() and count_tokens(body + sentence) > max_tokens:
                line_chunks.append(body)
                body = ""
            body += sentence + gap
        line_chunks.append(body)
        line_chunks[-1] += newlines
        raw.extend(line_chunks)
    out = []
    for chunk in raw:
        if not chunk:
            continue
        chunk = re.sub(rf"{marker}(\d+){marker}", lambda m: saved[int(m.group(1))], chunk)
        stripped = chunk.rstrip()
        out.append((stripped, chunk[len(stripped):]))
    return out


# lines that are structure, not prose: never sent to the AI
STRUCTURE_LINE = re.compile(r"^\s*(#|\||```|~~~|<[a-zA-Z/!])")
# list markers kept outside the AI: "- ", "* ", "1. ", "2) "
LIST_PREFIX = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def sentences_with(text, fragments):
    """The full sentences of `text` that contain each fragment (used to tell the AI exactly what to keep)."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found = []
    for frag in fragments:
        for sent in sentences:
            if frag.lower() in sent.lower() and sent not in found:
                found.append(sent)
                break
    return found


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
        words = _content_words(m.group(2))
        # "only" may stand in for the negation only in rules about others ("not ... of other sellers")
        allow_only = re.search(r"\b(other|others|else|anyone|anybody)\b", m.group(2)) is not None
        # kept if at least one subject word survives with a negation right before it
        if words and not any(_negated(w, after_words, allow_only=allow_only) for w in words):
            lost.append(f"{m.group(1)}{m.group(2)}".strip())
    return lost


def added_constraints(before, after):
    """Negative rules in `after` that `before` never had: "Before coding, plan..." -> "No code." """
    added = []
    before_words = _words(before)
    for m in re.finditer(rf"\b{NEGATIONS}\b((?:\s+[\w']+){{1,4}})", after.lower()):
        words = _content_words(m.group(2))
        # "only" in the original also counts ("see only their own" -> "not other sellers'")
        if words and not any(_negated(w, before_words, allow_only=True) for w in words):
            added.append(f"{m.group(1)}{m.group(2)}".strip())
    return added


# order of steps and plans: "first X, then Y", "simulate payments for now, integrate later"
SEQUENCE_GROUPS = {
    "first/before": r"\b(first|before|beforehand|initially|to start|start by|start with)\b",
    "for now": r"\b(for now|currently|at the moment|right now|to begin with|at first)\b",
    "later": r"\b(later|future|eventually|afterwards|down the line|next phase|in a later)\b",
    "then/after": r"\b(then|after|once)\b",
}

def lost_sequence(before, after):
    """Order-of-steps and plan words that disappeared ("first", "for now", "later")."""
    return [name for name, pattern in SEQUENCE_GROUPS.items()
            if re.search(pattern, before, re.IGNORECASE) and not re.search(pattern, after, re.IGNORECASE)
            and name != "then/after"]       # "then/after" is often implied by "first"; too strict to require


def lost_requests(before, after):
    """Requests joined with "and / also / plus" ("a poem ... and also a haiku ... and a limerick"):
    the first content word after each one must survive."""
    lost = []
    after_words = _words(after)
    for m in re.finditer(r"\b(and|also|plus)\b((?:\s+[\w']+){1,4})", before.lower()):
        # skip verbs ("and explain why...") and negations ("and never modifies...")
        words = _content_words(m.group(2), extra_skip=REQUEST_VERBS)
        if not words:
            # only a verb follows ("and explain how everything will work"): the verb is the request.
            # Just a real request verb right after "and" -- not helpers like do/give/make/use
            first = (_words(m.group(2)) or [""])[0]
            if (first in REQUEST_VERBS and first not in GENERIC_VERBS and first not in NOT_SUBJECTS
                    and first not in {"do", "go", "let", "add", "keep", "note", "help"}
                    and not re.search(rf"\b{NEGATIONS}\b", m.group(2))):
                words = [first]
        if words and not any(_same_word(a, w) for w in words for a in after_words):
            lost.append(words[0])
    return lost


def keyword_overlap(original, rewritten):
    """Share of the original's key words still in the rewrite (0.0 to 1.0).
    Words are compared by their first 4 letters, so 'lyrics' matches 'lyrical' and 'dicts'
    matches 'dictionaries'. Negations, helper verbs and Roman Urdu function words don't count.
    Works for any script; Chinese/Japanese/Korean are compared by character pairs."""
    def keys(t):
        if script_of(t) == "cjk":
            chars = [c for c in t if c.isalpha()]
            return {a + b for a, b in zip(chars, chars[1:])}
        min_len = 3 if script_of(t) in ("latin", "none") else 1
        return {w[:4] for w in _words(t)
                if len(w) > min_len and w not in STOPWORDS and w not in GENERIC_VERBS
                and w not in NOT_SUBJECTS and w not in ROMAN_URDU_FUNCTION and not re.fullmatch(NEGATIONS, w)}
    orig = keys(original)
    if len(orig) < 4:
        return 1.0      # too few key words to judge (e.g. short, misspelled prompts)
    return len(orig & keys(rewritten)) / len(orig)


COMMAND_WORDS = {"npm", "pip", "git", "cd", "ls", "sudo", "py", "node", "yarn", "curl", "wget", "www"}

def capitalize_first(text):
    """Capitalize the first letter, but not words like iPhone, npm, e.g., paths or URLs."""
    first = text.split(None, 1)[0] if text.strip() else ""
    core = first.rstrip(".,!?;:")              # "explain." is a word, "e.g." and "x.com" are not
    if (not core or any(c.isupper() for c in core[1:]) or re.search(r"[./\\:_\-@\d]", core)
            or core.lower() in COMMAND_WORDS):
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
