import re
import time
import ollama
from token_counter import count_tokens

MODEL = "gemma3:4b"          # used to compress the prompt
SPELL_MODEL = "gemma3:4b"    # used to fix spelling (can be a smaller model later)

# a client with a timeout, so the program can never hang forever
client = ollama.Client(timeout=120)


# ---------- Step 1: spelling ----------
SPELL_SYSTEM = """You fix spelling in prompts. Change NOTHING else.
- Fix typos (doig -> doing, revrsal -> reversal, hlp -> help).
- Fix the wrong word when context makes it clear (rite method -> write method).
- Expand texting short forms (r -> are, u -> you, dat -> that, ur -> your, ary -> array).
- Keep every word, greeting, question and punctuation mark otherwise. Do not shorten.
- Roman Urdu words are not typos. Leave them as they are. Never translate.
- Keep text inside quotes or code exactly as written.
- Do NOT answer the prompt.
- Put the corrected prompt between <prompt> and </prompt>. Write nothing else.

Example:
Original: hi how r u doig? can u hlp me rite a leter to my boss
Output: <prompt>hi how are you doing? can you help me write a letter to my boss</prompt>"""


# ---------- Step 3: compression ----------
COMPRESS_SYSTEM = """You compress prompts so they use fewer tokens, without changing what is asked.
- Keep every request and question. Never drop one.
- Keep names, numbers, limits and constraints ("500 words", "no code").
- Keep text inside quotes or code exactly as written.
- Keep the same language. Roman Urdu stays Roman Urdu. Never translate.
- Remove anything polite or chatty that is still left. Use the shortest clear wording.
- Do NOT answer or carry out the prompt. Only rewrite it.
- Put the rewritten prompt between <prompt> and </prompt>. Write nothing else.

Examples:
Original: Help me to write method for array reversal?
Output: <prompt>Write a method to reverse an array.</prompt>

Original: I want you to write me an email to my boss because I will be absent tomorrow as I am sick.
Output: <prompt>Write a sick-leave email to my boss for tomorrow.</prompt>"""


def clean(text):
    """Pull the rewritten prompt out of the model's reply."""
    text = text.strip()

    # 1. best case: the model used the <prompt> tags
    match = re.search(r"<prompt>(.*?)(</prompt>|$)", text, flags=re.S | re.I)
    if match:
        text = match.group(1).strip()
    else:
        # 2. fallback: remove a label like "**Rewritten prompt:**" at the start
        text = re.sub(r"^\W*(here is|here's|optimized|rewritten|compressed|corrected|output)[^:\n]*:\W*", "", text, flags=re.I)
        # and drop an explanation the model added after a blank line
        text = text.split("\n\n")[0].strip()

    # 3. curly quotes -> straight quotes, so protected text still matches
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # 4. remove quotes around the WHOLE prompt only, never a title's own quotes
    if len(text) > 1 and text[0] == text[-1] == '"' and text.count('"') == 2:
        text = text[1:-1].strip()
    return text


def ask(system, prompt, model):
    """Send one prompt to the local model and return the cleaned reply."""
    start = time.perf_counter()
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Original: {prompt}\nOutput:"},
        ],
        options={
            "temperature": 0,     # same input -> same output
            "num_predict": 200,   # max tokens the model may write
            "num_ctx": 2048,      # smaller context window = faster
        },
        keep_alive="30m",         # keep the model loaded for 30 minutes
    )
    seconds = time.perf_counter() - start
    return clean(response["message"]["content"]), seconds


def spell_fix(prompt):
    return ask(SPELL_SYSTEM, prompt, SPELL_MODEL)


def llm_optimize(prompt):
    return ask(COMPRESS_SYSTEM, prompt, MODEL)


if __name__ == "__main__":
    prompt = input("Paste your prompt: ")
    fixed, t1 = spell_fix(prompt)
    print(f"Spell fixed ({t1:.1f}s): {fixed}")
    short, t2 = llm_optimize(fixed)
    print(f"Compressed  ({t2:.1f}s): {short}")
