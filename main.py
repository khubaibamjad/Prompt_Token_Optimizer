from token_counter import count_tokens, compare_models
from optimizer import optimize
from llm_optimizer import llm_optimize
from scorer import rate, grade

USE_AI = True

def pipeline(prompt):
    rules_version=optimize(prompt)
    final=rules_version
    if USE_AI:
        try:
            ai_version = llm_optimize(prompt)
            if count_tokens(ai_version)<count_tokens(rules_version):
                final=ai_version
            else:
                print("(AI rewrite wasn't shorter, keeping the rules version)")
        except Exception as e:
            print(f"(AI step skipped: {e})")   # e.g. Ollama isn't running
    return rules_version, final

def report(prompt, final):
    before_score, _ = rate(prompt)
    after_score, details = rate(final)
    before_tokens = count_tokens(prompt)
    after_tokens = count_tokens(final)
    saved = before_tokens - after_tokens

    print("\n" + "=" * 50)
    print("ORIGINAL :", prompt)
    print("OPTIMIZED:", final)
    print("=" * 50)
    print(f"Tokens : {before_tokens} → {after_tokens}  (saved {saved}, {saved / before_tokens:.0%})")
    print(f"Score  : {before_score} ({grade(before_score)}) → {after_score} ({grade(after_score)})")

    print("\nDetails for the optimized prompt:")
    for name, (score, note) in details.items():
        print(f"  {name:<12} {score:>3}/100   {note}")

    compare_models(final)


if __name__ == "__main__":
    prompt = input("Paste your prompt: ").strip()
    if not prompt:
        print("Empty prompt.")
        exit()

    rules_version, final = pipeline(prompt)
    report(prompt, final)
