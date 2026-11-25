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
        result = re.sub(re.escape(phrase), replacement, result, flags=re.IGNORECASE)
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

def remove_greeting(text):
    # removes greetings like "hello", "hi bhai", "salam sir" only at the START, as whole words
    return re.sub(
        r"^\s*(hello|hi|hey|dear|salam|assalam[u-]?\s?o?\s?alaikum|aoa)\b[,!.]?"
        r"(\s+(bhai|bro|sir|yaar|janab|there|team|all|everyone)\b[,!.]?)?\s*",
        "", text, flags=re.IGNORECASE)

def remove_closing_thanks(text):
    # removes "Thank you so much in advance for your help!" etc., but only at the END
    return re.sub(
        r"[\s,.!]*\b(thank you|thanks|thx|shukriya|shukria)( so much| very much| a lot)?( in advance)?( for (your|the) help)?[.!]*\s*$",
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
    return len(orig & keys(rewritten)) / len(orig) if orig else 1.0


def optimize(text):
    text, saved = protect(text)
    text = remove_repeated_words(text)
    text = remove_greeting(text)
    text = remove_closing_thanks(text)
    text = remove_filler(text)
    text = remove_decorations(text)
    text = collapse_punctuation(text)
    text = collapse_whitespace(text)
    text = remove_duplicate_sentences(text)
    text = text.strip()
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