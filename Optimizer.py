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
    " for me ": "",
}


def remove_filler(text):
    result = text
    for phrase, replacement in FILLER.items():
        result = re.sub(re.escape(phrase), replacement, result, flags=re.IGNORECASE)
    return result

def collapse_whitespace(text):
    text = re.sub(r"[ \t]+", " ", text)     # many spaces/tabs → one space
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3+ newlines → one blank line
    return text

def remove_greeting(text):
    # removes "hello", "hi", "hey", "dear" only at the START, as whole words
    return re.sub(r"^\s*(hello|hi|hey|dear)\b[,!.]?\s*", "", text, flags=re.IGNORECASE)

def collapse_punctuation(text):
    text = re.sub(r"([?!.])\1+", r"\1", text)   # ?? → ?   !!! → !
    text = re.sub(r"\s+([?!.,])", r"\1", text)  # "it ?" → "it?"
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



def optimize(text):
    text = remove_greeting(text)
    text = remove_filler(text)
    text = collapse_punctuation(text)
    text = collapse_whitespace(text)
    text = remove_duplicate_sentences(text)
    text = text.strip()
    return text[:1].upper() + text[1:]      # capitalize the first letter

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