import re
import ollama
import time
from token_counter import count_tokens
from optimizer import optimize

MODEL = "gemma3:4b"

SYSTEM = """You rewrite prompts to use fewer tokens.
Rules:
- Keep EVERY question and request from the original. Never drop one.
- Keep the exact same meaning, names, numbers and constraints.
- Fix spelling mistakes.
- Remove greetings, filler, politeness and repetition.
- Do NOT answer the prompt. Only rewrite it.
- Output ONLY the rewritten prompt. No quotes, no explanation."""

# a client with a timeout, so the program can never hang forever
client = ollama.Client(timeout=120)

def clean(text):
    # small models sometimes add a label or quotes, so strip them
    text = re.sub(r"^(here is|here's|optimized prompt|rewritten prompt)[^:]*:\s*", "", text.strip(), flags=re.I)
    return text.strip().strip('"').strip()

def llm_optimize(prompt):
    start = time.perf_counter()                 # start the timer

    response = client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Rewrite this prompt:\n{prompt}"},
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