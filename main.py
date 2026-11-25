from token_counter import count_tokens, compare_models
from optimizer import optimize
from llm_optimizer import llm_optimize
from scorer import rate, grade, split_scores

USE_AI = True

def pipeline(prompt):
    rules_version=optimize(prompt)
    final=rules_version
    if USE_AI:
        try:
            ai_version = llm_optimize(rules_version)
            if count_tokens(ai_version)<count_tokens(rules_version):
                final=ai_version
            else:
                print("(AI rewrite wasn't shorter, keeping the rules version)")
        except Exception as e:
            print(f"(AI step skipped: {e})")   # e.g. Ollama isn't running
    return rules_version, final

def report(prompt, final):
    before_score, before_details = rate(prompt)          # ← changed: keep before_details
    after_score, details = rate(final)
    before_tokens = count_tokens(prompt)
    after_tokens = count_tokens(final)
    saved = before_tokens - after_tokens

    b_cost, b_quality = split_scores(before_details)      # ← new
    a_cost, a_quality = split_scores(details)             # ← new

    print("\n" + "=" * 50)
    print("ORIGINAL :", prompt)
    print("OPTIMIZED:", final)
    print("=" * 50)
    print(f"Tokens        : {before_tokens} → {after_tokens}  (saved {saved}, {saved / before_tokens:.0%})")
    print(f"Cost score    : {b_cost} → {a_cost}   (how token-efficient)")        # ← new
    print(f"Quality score : {b_quality} → {a_quality}   (how clear and complete)")  # ← new

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
