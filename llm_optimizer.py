import re
import ollama
import time
from token_counter import count_tokens
from optimizer import optimize

MODEL = "gemma3:4b"

SYSTEM = """You compress prompts so they use fewer tokens, without changing what is asked.

ALWAYS REMOVE:
- Greetings and names at the start: hello, hi, hey, dear, salam, bhai, sir, bro, baby, yaar.
- Please and its forms: please, plz, pls, kindly.
- Thanks at the end: thank you, thanks, shukriya, thank you in advance.
- Small talk: "I hope you are doing well", "how are you" (only when the prompt also asks for something else).
- Filler: "I would like you to", "can you", "could you", "go ahead and", "basically", "actually",
  "it is important to note that", "make sure that", "for me".
- Repeated words, repeated sentences, extra punctuation like ??? or !!!, and decorations like ---- or ====.

ALWAYS KEEP:
- Every real question and request. Never drop one.
- Names, numbers, limits and constraints (for example "500 words", "do not include code").
- Text inside quotes or code exactly as written.
- The same language as the original. Roman Urdu stays Roman Urdu. Never translate.

ALSO:
- Fix spelling mistakes (hlp -> help, luv -> love).
- Use the shortest clear wording.
- Do NOT answer or carry out the prompt. Only rewrite it.
- Put the rewritten prompt between <prompt> and </prompt>. Write nothing else.

Examples:
Original: Hello, can you please write me something like an email to my boss because I am sick and can't come tomorrow? Thank you!
Output: <prompt>Write a short sick-leave email to my boss for tomorrow.</prompt>

Original: Hi babay how are you doing plz hlp me i luv u
Output: <prompt>Help me. I love you.</prompt>

Original: Hello bhai please mujhe ek email likh do manager ko ke main kal office nahi aa sakta, thank you so much
Output: <prompt>Manager ko email likho ke main kal office nahi aa sakta.</prompt>"""

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