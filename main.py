import re
import sys
from token_counter import count_tokens, compare_models
from optimizer import (optimize, pre_clean, protected_parts, keyword_overlap, lost_constraints,
                       lost_requests, normalize_quotes, script_of)
from llm_optimizer import (spell_fix, llm_optimize, needs_spell_fix, MAX_AI_TOKENS,
                           remember_spell, forget_spell, remember_compression, forget_compression)
from scorer import rate, grade, split_scores

USE_AI = True

# common Roman Urdu words; if the input has them and the output doesn't, it was translated
ROMAN_URDU = {"hai", "ho", "mujhe", "karo", "likh", "likho", "nahi", "bhai", "ka", "ki", "ke",
              "mein", "main", "kya", "aap", "apne", "mera", "meri", "kar", "do", "se", "ko"}


def missing_protected(before, after):
    """Quoted text and code from `before` that isn't in `after` (curly and straight quotes count as the same)."""
    after_n = normalize_quotes(after)
    return [p for p in protected_parts(before) if normalize_quotes(p) not in after_n]


def restore_quote_style(original, text):
    """Put the user's own curly quotes back after the AI straightened them."""
    for part in protected_parts(original):
        plain = normalize_quotes(part)
        if plain != part and part not in text:
            text = text.replace(plain, part, 1)
    return text


def changed_language(before, after):
    """Why the output is in a different language or script than the input, or ''."""
    s_before, s_after = script_of(before), script_of(after)
    if "none" not in (s_before, s_after) and s_before != s_after:
        return f"script changed from {s_before} to {s_after}"
    words_before = re.findall(r"[a-z]+", before.lower())
    urdu_before = sum(w in ROMAN_URDU for w in words_before)
    if urdu_before >= 3:
        urdu_after = sum(w in ROMAN_URDU for w in re.findall(r"[a-z]+", after.lower()))
        if urdu_after < urdu_before / 2:
            return "Roman Urdu was translated or dropped"
    return ""


def spelling_is_safe(original, fixed):
    """A spell fix must keep quoted text, numbers and negations, the same language,
    and stay about the same length."""
    if not fixed:
        return False, "empty result"
    missing = missing_protected(original, fixed)
    if missing:
        return False, f"changed protected text {missing}"
    lost = lost_constraints(original, fixed, check_subjects=False)
    if lost:
        return False, f"lost rules or numbers: {lost}"
    why = changed_language(original, fixed)
    if why:
        return False, why
    before, after = count_tokens(original), count_tokens(fixed)
    ratio = after / max(before, 1)
    if not (0.85 <= ratio <= 1.3 or abs(after - before) <= 3):   # small prompts may shift a few tokens
        return False, f"length changed too much ({ratio:.2f}x), it probably rewrote, cut or answered"
    return True, ""


def compression_is_safe(before, after):
    """A compressed prompt must keep quoted text, rules, numbers, every request,
    the same language, most key words, and be shorter."""
    if not after.strip():
        return False, "empty result"
    missing = missing_protected(before, after)
    if missing:
        return False, f"changed protected text {missing}"
    lost = lost_constraints(before, after)
    if lost:
        return False, f"lost rules or numbers: {lost}"
    dropped = lost_requests(before, after)
    if dropped:
        return False, f"dropped requests: {dropped}"
    why = changed_language(before, after)
    if why:
        return False, why
    overlap = keyword_overlap(before, after)
    if overlap < 0.7:
        return False, f"kept only {overlap:.0%} of the key words, it probably changed the meaning"
    if count_tokens(after) >= count_tokens(before):
        return False, "not shorter"
    return True, ""


def show(step, text):
    print(f"  [{step:<11}] {count_tokens(text):>3} tokens | {text[:150]}")


def pipeline(prompt):
    print()
    show("original", prompt)

    # Step 0: cheap cleanup (stretched letters, keyboard spam, symbol junk)
    text = pre_clean(prompt)
    if text != prompt:
        show("0 pre-clean", text)

    use_ai = USE_AI
    if use_ai and count_tokens(text) > MAX_AI_TOKENS:
        print(f"  [AI         ] skipped: prompt is over {MAX_AI_TOKENS} tokens, the model could cut it short")
        use_ai = False

    # Step 1: fix spelling FIRST, because every rule depends on correct words
    if use_ai and not needs_spell_fix(text):
        print("  [1 spell    ] skipped: no typos found")
    elif use_ai:
        try:
            fixed, secs = spell_fix(text)
            ok, why = spelling_is_safe(text, fixed)
            if ok:
                remember_spell(text, fixed)          # only accepted answers are cached
                text = restore_quote_style(text, fixed)
                show("1 spell " + (f"{secs:.1f}s" if secs else "cache"), text)
            else:
                forget_spell(text)                   # a bad cached answer gets retried next time
                print(f"  [1 spell    ] rejected: {why}")
        except Exception as e:
            print(f"  [1 spell    ] skipped: {e}")   # e.g. Ollama isn't running, or output cut off

    # Step 2: rules (greetings, please, thanks, small talk, filler, duplicates, symbols)
    rules_version = optimize(text)
    if not rules_version.strip():
        print("  [2 rules    ] removed everything (greeting or politeness only), keeping the original prompt")
        return prompt, prompt
    show("2 rules", rules_version)

    # Step 3: AI compression, only worth it for longer prompts
    final = rules_version
    if use_ai and count_tokens(rules_version) > 8:
        try:
            raw, secs = llm_optimize(rules_version)
            short = optimize(raw)                    # clean the AI output with the rules too
            ok, why = compression_is_safe(rules_version, short)
            if ok:
                remember_compression(rules_version, raw)
                final = restore_quote_style(rules_version, short)
                show("3 AI " + (f"{secs:.1f}s" if secs else "cache"), final)
            else:
                forget_compression(rules_version)
                print(f"  [3 AI       ] rejected: {why} -> {short[:100]}")
        except Exception as e:
            print(f"  [3 AI       ] skipped: {e}")
    return rules_version, final

def report(prompt, final):
    before_score, before_details = rate(prompt)
    after_score, details = rate(final)
    before_tokens = count_tokens(prompt)
    after_tokens = count_tokens(final)
    saved = before_tokens - after_tokens

    b_cost, b_quality = split_scores(before_details)
    a_cost, a_quality = split_scores(details)

    print("\n" + "=" * 50)
    print("ORIGINAL :", prompt)
    print("OPTIMIZED:", final)
    print("=" * 50)
    print(f"Tokens        : {before_tokens} → {after_tokens}  (saved {saved}, {saved / max(before_tokens, 1):.0%})")
    print(f"Cost score    : {b_cost} → {a_cost}   (how token-efficient)")
    print(f"Quality score : {b_quality} → {a_quality}   (how clear and complete)")

    print("\nDetails for the optimized prompt:")
    for name, (score, note) in details.items():
        print(f"  {name:<12} {score:>3}/100   {note}")

    compare_models(final)


def read_prompt(stream=None, interactive=None):
    """Read the whole prompt, including single blank lines between paragraphs.
    Stops at a line containing only END, at end of input (Ctrl+Z then Enter on Windows,
    Ctrl+D on Mac/Linux, or the end of piped input), or -- when typing in a terminal --
    at two empty lines in a row."""
    stream = stream or sys.stdin
    if interactive is None:
        interactive = stream.isatty()
    if interactive:
        print("Paste your prompt. When you're done, press Enter on two empty lines (or type END).")
    def next_line():
        # typing in the terminal: input() always hands over one line at a time
        if interactive and stream is sys.stdin:
            return input()                          # raises EOFError on Ctrl+Z / Ctrl+D
        line = stream.readline()
        if line == "":
            raise EOFError
        return line

    lines = []
    while True:
        try:
            line = next_line().rstrip("\r\n")
        except EOFError:
            break
        if line.strip() == "END":
            break
        if interactive and line == "" and lines and lines[-1] == "":
            break                                   # second empty line in a row
        lines.append(line)
    return "\n".join(lines).strip()


if __name__ == "__main__":
    try:
        prompt = read_prompt()
        if not prompt:
            print("Empty prompt.")
            sys.exit()
        rules_version, final = pipeline(prompt)
        report(prompt, final)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(1)
