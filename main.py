from token_counter import count_tokens, compare_models
from optimizer import optimize, protected_parts, keyword_overlap
from llm_optimizer import spell_fix, llm_optimize
from scorer import rate, grade, split_scores

USE_AI = True


def spelling_is_safe(original, fixed):
    """A spell fix must keep quoted text and stay about the same length."""
    if not fixed:
        return False, "empty result"
    missing = [p for p in protected_parts(original) if p not in fixed]
    if missing:
        return False, f"changed protected text {missing}"
    ratio = count_tokens(fixed) / max(count_tokens(original), 1)
    if not 0.6 <= ratio <= 1.6:
        return False, f"length changed too much ({ratio:.1f}x), it probably rewrote or answered"
    return True, ""


def compression_is_safe(before, after):
    """A compressed prompt must keep quoted text, key words, and be shorter."""
    missing = [p for p in protected_parts(before) if p not in after]
    if missing:
        return False, f"changed protected text {missing}"
    overlap = keyword_overlap(before, after)
    if overlap < 0.4:
        return False, f"kept only {overlap:.0%} of the key words, it probably answered instead of rewriting"
    if count_tokens(after) >= count_tokens(before):
        return False, "not shorter"
    return True, ""


def show(step, text):
    print(f"  [{step:<11}] {count_tokens(text):>3} tokens | {text[:150]}")


def pipeline(prompt):
    print()
    show("original", prompt)

    # Step 1: fix spelling FIRST, because every rule depends on correct words
    text = prompt
    if USE_AI:
        try:
            fixed, secs = spell_fix(prompt)
            ok, why = spelling_is_safe(prompt, fixed)
            if ok:
                text = fixed
                show(f"1 spell {secs:.1f}s", text)
            else:
                print(f"  [1 spell    ] rejected: {why}")
        except Exception as e:
            print(f"  [1 spell    ] skipped: {e}")   # e.g. Ollama isn't running

    # Step 2: rules (greetings, please, thanks, small talk, filler, duplicates, symbols)
    rules_version = optimize(text)
    show("2 rules", rules_version)

    # Step 3: AI compression, only worth it for longer prompts
    final = rules_version
    if USE_AI and count_tokens(rules_version) > 8:
        try:
            short, secs = llm_optimize(rules_version)
            short = optimize(short)              # clean the AI output with the rules too
            ok, why = compression_is_safe(rules_version, short)
            if ok:
                final = short
                show(f"3 AI {secs:.1f}s", final)
            else:
                print(f"  [3 AI       ] rejected: {why} -> {short[:100]}")
        except Exception as e:
            print(f"  [3 AI       ] skipped: {e}")
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
    print("Paste your prompt, then press Enter on an empty line:")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    prompt = "\n".join(lines).strip()

    if not prompt:
        print("Empty prompt.")
        exit()

    rules_version, final = pipeline(prompt)
    report(prompt, final)
