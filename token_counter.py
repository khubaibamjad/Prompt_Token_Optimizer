import sys
import tiktoken

MODELS = {
    "gpt-4":  "cl100k_base",
    "gpt-4o": "o200k_base"
}


DEFAULT_ENCODING = "o200k_base"
_ENCODERS = {}          # loaded once, reused on every call
_WARNED = set()


def get_encoder(model="gpt-4o"):
    """The tokenizer for a model. Unknown models fall back to o200k_base with a warning."""
    name = MODELS.get(model)
    if name is None:
        if model not in _WARNED:
            print(f"(unknown model '{model}', counting tokens with {DEFAULT_ENCODING})", file=sys.stderr)
            _WARNED.add(model)
        name = DEFAULT_ENCODING
    if name not in _ENCODERS:
        _ENCODERS[name] = tiktoken.get_encoding(name)
    return _ENCODERS[name]


def count_tokens(text, model="gpt-4o"):
    """Return the number of tokens."""
    return len(get_encoder(model).encode(text))

def show_tokens(text, model="gpt-4o"):
    """Print each token wrapped in [brackets]."""
    enc = get_encoder(model)
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
