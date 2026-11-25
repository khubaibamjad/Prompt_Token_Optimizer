import tiktoken

MODELS = {
    "gpt-4":  "cl100k_base",
    "gpt-4o": "o200k_base"
}


def count_tokens(text, model="gpt-4o"):
    """Return the number of tokens."""
    enc = tiktoken.get_encoding(MODELS[model])
    return len(enc.encode(text))

def show_tokens(text, model="gpt-4o"):
    """Print each token wrapped in [brackets]."""
    enc = tiktoken.get_encoding(MODELS[model])
    ids = enc.encode(text)
    pieces = [enc.decode([i]) for i in ids]
    print("Tokens:", "".join(f"[{p}]" for p in pieces))
    print("Count: ", len(ids))

def compare_models(text):
    """Print the token count for every model in MODELS."""
    print("\n--- Model comparison ---")
    for model in MODELS:
        print(f"{model:>7}: {count_tokens(text, model)} tokens")


if __name__ == "__main__":
    prompt = input("Paste your prompt: ")
    show_tokens(prompt)
    compare_models(prompt)
