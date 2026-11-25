import re
import ollama
import time
from token_counter import count_tokens
from optimizer import optimize

MODEL = "gemma3:4b"

SYSTEM = """You compress prompts so they use fewer tokens.
Rules:
- Keep EVERY question and request from the original. Never drop one.
- Keep the exact same meaning, names, numbers and constraints.
- Keep text inside quotes exactly as written.
- Fix spelling mistakes.
- Remove greetings, filler, politeness and repetition. Use shorter wording.
- Do NOT answer or carry out the prompt. Only rewrite it.
- Put the rewritten prompt between <prompt> and </prompt>. Write nothing else.

Example:
Original: Hello, can you please write me something like an email to my boss because I am sick and can't come tomorrow?
Output: <prompt>Write a short sick-leave email to my boss for tomorrow.</prompt>"""

# a client with a timeout, so the program can never hang forever
client = ollama.Client(timeout=120)


def clean(text):
    """Pull the rewritten prompt out of the model's reply."""
    text = text.strip()

    # 1. best case: the model used the <prompt> tags
    match = re.search(r"<prompt>(.*?)(</prompt>|$)", text, flags=re.S | re.I)
    if match:
        text = match.group(1).strip()
    else:
        # 2. fallback: remove a label like "**Rewritten prompt:**" at the start
        text = re.sub(r"^\W*(here is|here's|optimized|rewritten|compressed|output)[^:\n]*:\W*", "", text, flags=re.I)
        # and drop an explanation the model added after a blank line
        text = text.split("\n\n")[0].strip()

    # 3. curly quotes -> straight quotes, so protected text still matches
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    # 4. remove quotes around the WHOLE prompt only, never a title's own quotes
    if len(text) > 1 and text[0] == text[-1] == '"' and text.count('"') == 2:
        text = text[1:-1].strip()
    return text


def llm_optimize(prompt):
    start = time.perf_counter()                 # start the timer

    response = client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Original: {prompt}\nOutput:"},
        ],
        options={
            "temperature": 0,     # same input → same output
            "num_predict": 150,   # max tokens the model may write
            "num_ctx": 2048,      # smaller context window = faster
        },
        keep_alive="30m",         # keep the model loaded for 30 minutes
    )

    print(f"(AI took {time.perf_counter() - start:.1f}s)")
    return clean(response["message"]["content"])

if __name__ == "__main__":
    prompt = input("Paste your prompt: ")

    step1 = optimize(prompt)          # free rules first
    step2 = llm_optimize(step1)       # then the local model

    # safety check: reject the model's version if it didn't save tokens
    if count_tokens(step2) >= count_tokens(step1):
        print("(model's rewrite wasn't shorter, keeping the rules version)")
        step2 = step1

    print(f"\nOriginal ({count_tokens(prompt):>3} tokens): {prompt}")
    print(f"Rules    ({count_tokens(step1):>3} tokens): {step1}")
    print(f"Model    ({count_tokens(step2):>3} tokens): {step2}")