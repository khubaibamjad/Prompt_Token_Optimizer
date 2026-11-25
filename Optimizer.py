import re 
from token_counter import count_tokens

FILLER = {
    "i would like you to ": "",
    "could you please ": "",
    "can you please ": "",
    "please ": "",
    "go ahead and ": "",
    "in order to ": "to ",
    "due to the fact that ": "because ",
    "at this point in time": "now",
    "a large number of ": "many ",
    "it is important to note that ": "",
    "basically ": "",
    "actually ": "",
    " for me": "",
}


def remove_filler(text):
    result = text
    for phrase, replacement in FILLER.items():
        # \b = whole words only, so "please " can't match inside "pplease "
        pattern = (r"\b" if phrase[0].isalnum() else "") + re.escape(phrase)
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    # misspelled or short forms of "please": plz, pls, plzz, pleaseee, pplease
    result = re.sub(r"\b(p+l+e*a*s+e*|pl[sz]+)\b\s*", "", result, flags=re.IGNORECASE)
    return result

def remove_repeated_words(text):
    # "hello hello" → "hello",  "the the" → "the"
    return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)

def remove_decorations(text):
    # "---====" or "*****" → removed, but keeps "well-known" and "**bold**"
    return re.sub(r"([-=_*#~])\1{2,}", " ", text)

def collapse_whitespace(text):
    text = re.sub(r"[ \t]+", " ", text)     # many spaces/tabs → one space
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3+ newlines → one blank line
    return text

def shrink_stretched_letters(text):
    # "appp" -> "app", "chaaaal" -> "chaal", "sureee" -> "suree" (the spell step fixes the rest)
    # only lowercase and never "w", so "www." and Roman numerals like "III" stay intact
    return re.sub(r"([a-vx-z])\1{2,}", r"\1\1", text)

def remove_keyboard_spam(text):
    # button-mashing like "plslplsplsplsplpsl": words made only of p, l, s, z (with both p and l)
    return re.sub(r"\b(?=[plsz]*p)(?=[plsz]*l)[plsz]{3,}\b\s*", "", text, flags=re.IGNORECASE)

def remove_symbol_junk(text):
    # 4+ mixed symbols like "???????_))(__)()(_(" -> "?"  (keeps one ? ! or . if the run started with it)
    def keep_first(m):
        return m.group(0)[0] if m.group(0)[0] in "?!." else " "
    return re.sub(r"(?:[^\w\s]|_){4,}", keep_first, text)

def pre_clean(text):
    """Cheap fixes that help the spell step: stretched letters, spam, symbol junk.
    Quoted text and code stay protected."""
    text, saved = protect(text)
    text = shrink_stretched_letters(text)
    text = remove_keyboard_spam(text)
    text = remove_symbol_junk(text)
    text = collapse_whitespace(text).strip()
    return restore(text, saved)


def remove_greeting(text):
    # removes greetings like "hello", "hi bhai", "salam sir" only at the START, as whole words
    return re.sub(
        r"^\s*(hello|hi|hey|dear|salam|salaam|assalam[u-]?\s?o?\s?alaikum|aoa)\b[,!.]?"
        r"(\s+((mere|meri|my|dear)\s+)?(bhai|bro|sir|yaar|janab|there|team|all|everyone|baby|babe|babay|jaan|dost|friend)\b[,!.]?)?\s*",
        "", text, flags=re.IGNORECASE)

def remove_pleasantries(text):
    # "I hope you are doing well today." adds tokens but nothing to the task
    return re.sub(r"\bI hope (you are|you're|u r) doing (well|good|fine)( today)?[.!]?\s*", "", text, flags=re.IGNORECASE)

def remove_small_talk(text):
    """Remove "how are you doing?" and "can you do that?" -- but only when
    something else is left, because sometimes "how are you" IS the question."""
    cleaned = re.sub(r"\bhow (are|r) (you|u)( doing| today)?\s*[?.!]*\s*", "", text, flags=re.IGNORECASE)
    # Roman Urdu: "kese ho aap", "kya haal chaal hai apka"
    cleaned = re.sub(r"\b(kese|kaise|kesy|kaisay|kaisy|kesay|kesi|kaisi)\s+(ho|hain|hn|hai)(\s+(aap|ap|app|tum))?\s*[?.!]*\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bkya\s+haal(\s+chaal)?\s+(hai|he|h|hain)(\s+(apka|aapka|apkaa|tumhara))?\s*[?.!]*\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,]*\b(can|could|will) (you|u) (do|help with) (that|this|it)\s*[?.!]*\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned if len(cleaned.split()) >= 3 else text

def remove_closing_thanks(text):
    # removes "Thank you so much in advance for your help!" etc., but only at the END
    return re.sub(
        r"[\s,]*\b(thank you|thanks|thx|shukriya|shukria)( so much| very much| a lot)?( in advance)?( for (your|the) help)?[.!]*\s*$",
        "", text, flags=re.IGNORECASE)

def collapse_punctuation(text):
    text = re.sub(r"([?!.])\1+", r"\1", text)   # ?? → ?   !!! → !
    text = re.sub(r"\s+([?!.,])", r"\1", text)  # "it ?" → "it?"
    text = re.sub(r"([?!])[.?!]+", r"\1", text)  # "?." → "?"
    return text

def remove_duplicate_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text)   # split after . ! ?
    seen = set()
    kept = []
    for s in sentences:
        s = s.strip()
        key = s.lower()                  # compare ignoring capitals
        if s and key not in seen:
            seen.add(key)
            kept.append(s[:1].upper() + s[1:])   # capitalize each sentence
    return " ".join(kept)



# Text inside quotes or code must never be changed (titles, code, exact data).
PROTECTED = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”", re.DOTALL)

def protect(text):
    """Swap protected parts for placeholders the rules can't touch."""
    saved = []
    def stash(match):
        saved.append(match.group(0))
        return f"\uE000{len(saved) - 1}\uE001"
    return PROTECTED.sub(stash, text), saved

def restore(text, saved):
    """Put the protected parts back."""
    return re.sub("\uE000(\\d+)\uE001", lambda m: saved[int(m.group(1))], text)

def protected_parts(text):
    return PROTECTED.findall(text)


STOPWORDS = {"the", "and", "that", "this", "with", "for", "from", "your", "what", "when",
             "which", "about", "into", "have", "will", "would", "should", "could", "there",
             "want", "like", "something", "because", "feeling", "come", "just", "please",
             "very", "really", "some", "also", "make", "sure", "thank", "thanks", "tell"}

def keyword_overlap(original, rewritten):
    """Share of the original's key words still in the rewrite (0.0 to 1.0).
    Words are compared by their first 5 letters, so 'lyrics' matches 'lyrical'."""
    def keys(t):
        return {w[:5] for w in re.findall(r"[a-z]+", t.lower()) if len(w) > 3 and w not in STOPWORDS}
    orig = keys(original)
    if len(orig) < 4:
        return 1.0      # too few key words to judge (e.g. short, misspelled prompts)
    return len(orig & keys(rewritten)) / len(orig)


def optimize(text):
    text, saved = protect(text)
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
    text = text[:1].upper() + text[1:]      # capitalize the first letter
    return restore(text, saved)

if __name__ == "__main__":
    prompt = input("Paste your prompt: ")
    
    if not prompt.strip():
        print("Empty prompt, nothing to optimize.")
        exit() 
    
    better = optimize(prompt)

    before = count_tokens(prompt)
    after = count_tokens(better)
    saved = before - after

    print("\nOriginal :", prompt)
    print("Optimized:", better)
    print(f"\nTokens: {before} → {after}  (saved {saved}, {saved / before:.0%})")