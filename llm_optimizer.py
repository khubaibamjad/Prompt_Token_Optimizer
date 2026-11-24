import re
import ollama
from token_counter import count_tokens
from optimizer import optimize

MODEL = "gemma3:4b"

SYSTEM = """You rewrite prompts to use fewer tokens.
Rules:
- Keep the exact same meaning, names, numbers and constraints.
- Remove greetings, filler, politeness and repetition.
- Do NOT answer the prompt. Only rewrite it.
- Output ONLY the rewritten prompt. No quotes, no explanation."""

def clean(text):
    # small models sometimes add a label or quotes, so strip them
    text = re.sub(r"^(here is|here's|optimized prompt|rewritten prompt)[^:]*:\s*", "", text.strip(), flags=re.I)
    return text.strip().strip('"').strip()

def llm_optimize(prompt):
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Rewrite this prompt:\n{prompt}"},
        ],
        options={"temperature": 0},
    )
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