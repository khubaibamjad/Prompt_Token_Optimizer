import re
import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from token_counter import count_tokens, compare_models
from optimizer import (optimize, pre_clean, protected_parts, keyword_overlap, lost_constraints,
                       lost_requests, normalize_quotes, script_of, sentences_with, split_chunks,
                       added_constraints, lost_sequence, STRUCTURE_LINE, LIST_PREFIX)
import llm_optimizer
from llm_optimizer import (spell_fix, llm_optimize, needs_spell_fix, MAX_AI_TOKENS, MODEL, SPELL_MODEL,
                           remember_spell, forget_spell, remember_compression, forget_compression)
from scorer import rate, grade, split_scores

USE_AI = True

# prompts longer than this are shortened in chunks of a few sentences: a small model
# keeps every rule much more reliably in short pieces, and one bad piece only costs that piece
CHUNK_ABOVE = 80        # tokens
CHUNK_SIZE = 60         # tokens per chunk
# a few sentences have few key words, so a good paraphrase ("platform" -> "marketplace") changes a
# big share of them; chunks still get every other check (rules, numbers, requests, quotes, language)
CHUNK_MIN_OVERLAP = 0.5
# big prompts (documents, specs) run in a faster mode: bigger chunks, tiny pieces skipped,
# no retries, and several chunks sent to Ollama at the same time
BIG_PROMPT = 600            # tokens
BIG_CHUNK_SIZE = 120        # tokens per chunk in big prompts
BIG_MIN_CHUNK = 20          # smaller pieces in big prompts only get the rule cleanup
PARALLEL = 3                # chunks sent to Ollama at once
SPELL_CHUNK_SIZE = 120  # tokens per chunk for the spell step (it only fixes typos, so bigger is fine)
# a single AI call never gets more than MAX_AI_TOKENS (bigger prompts are chunked);
# only truly huge prompts skip the AI altogether
MAX_PROMPT_TOKENS = 50000
# whole prompts need 60% of key words: terse rewrites swap many words, and every rule, number,
# request, invented rule and step order is checked separately anyway

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


def _word_count(text):
    """Number of words, counting a run of the same word ("hi hi hi") once."""
    words = re.findall(r"\w+", text.lower())
    return sum(1 for i, w in enumerate(words) if i == 0 or w != words[i - 1])


def kept_correct_words(original, fixed):
    """Share of the correctly spelled words in `original` that are still in `fixed`.
    A spelling fix keeps them; a model that answers or rewrites the prompt doesn't."""
    fixed_words = set(re.findall(r"\w+", fixed.lower()))
    words = list(dict.fromkeys(re.findall(r"[a-z]+", original.lower())))
    speller = llm_optimizer.SPELLER
    known = [w for w in words if speller is not None and len(w) > 1 and w in speller]
    if len(known) >= 3:
        return sum(w in fixed_words for w in known) / len(known), 0.75
    # no dictionary, or mostly non-English (Roman Urdu): compare all words by their first 4 letters
    words = [w for w in re.findall(r"\w+", original.lower()) if len(w) > 1]
    if len(words) < 3:
        return 1.0, 0.0
    prefixes = {w[:4] for w in fixed_words}
    return sum(w[:4] in prefixes for w in words) / len(words), 0.6


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
    kept, needed = kept_correct_words(original, fixed)
    if kept < needed:
        return False, f"kept only {kept:.0%} of the correctly spelled words, it probably answered or rewrote"
    # compare WORDS, not tokens: fixing junk like "plaeaessesse" -> "please" saves many tokens
    # but keeps the number of words. Repeats ("hi hi hi") are counted once.
    before, after = _word_count(original), _word_count(fixed)
    ratio = after / max(before, 1)
    # 0.7 (not 0.85): fixing typos merges repeats ("helo hello" -> "hello hello"); answers and
    # cut-off output are already caught by kept_correct_words above
    if not (0.7 <= ratio <= 1.3 or abs(after - before) <= 2):    # small prompts may shift a word or two
        return False, f"length changed too much ({ratio:.2f}x words), it probably rewrote, cut or answered"
    return True, ""


def compression_is_safe(before, after, min_overlap=0.6):
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
    added = added_constraints(before, after)
    if added:
        return False, f"added rules the original doesn't have: {added}"
    order = lost_sequence(before, after)
    if order:
        return False, f"lost the order or plan ({', '.join(order)})"
    why = changed_language(before, after)
    if why:
        return False, why
    overlap = keyword_overlap(before, after)
    if overlap < min_overlap:
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
    if use_ai and count_tokens(text) > MAX_PROMPT_TOKENS:
        print(f"  [AI         ] skipped: prompt is over {MAX_PROMPT_TOKENS} tokens")
        use_ai = False

    # Step 1: fix spelling FIRST, because every rule depends on correct words
    if use_ai:
        text = spell_step(text)

    # Step 2: rules (greetings, please, thanks, small talk, filler, duplicates, symbols)
    rules_version = optimize(text)
    if not rules_version.strip():
        print("  [2 rules    ] removed everything (greeting or politeness only), keeping the original prompt")
        return prompt, prompt
    show("2 rules", rules_version)

    # Step 3: AI compression, only worth it for longer prompts
    final = rules_version
    if use_ai and count_tokens(rules_version) > 8:
        if count_tokens(rules_version) > CHUNK_ABOVE:
            final = compress_in_chunks(rules_version)
        else:
            final = compress(rules_version, "3 AI") or rules_version
    return rules_version, final

def compress(text, label, verbose=True, min_overlap=0.6, retry=True):
    """Shorten `text` with the AI: one try, plus one retry told what was missing.
    Returns the safe shorter version, or None if both tries were rejected."""
    feedback = ""
    for attempt in (1, 2):
        name = label if attempt == 1 else label + " retry"
        try:
            raw, secs = llm_optimize(text, feedback)
        except Exception as e:
            print(f"  [{name:<11}] skipped: {e}")
            return None
        short = optimize(raw)                        # clean the AI output with the rules too
        ok, why = compression_is_safe(text, short, min_overlap)
        if ok:
            remember_compression(text, raw)          # only accepted answers are cached
            short = restore_quote_style(text, short)
            if verbose:
                show(name + " " + (f"{secs:.1f}s" if secs else "cache"), short)
            return short
        forget_compression(text)
        if verbose:
            print(f"  [{name:<11}] rejected: {why} -> {short[:300]}")
        # only retry when the model left something out; other problems won't improve
        if not retry or not why.startswith(("dropped requests", "lost rules or numbers", "kept only",
                                            "added rules", "lost the order")):
            return None
        missing = lost_constraints(text, short) + lost_requests(text, short)
        keep = sentences_with(text, missing)
        feedback = why.replace("dropped requests:", "dropped these requests:")
        if why.startswith("added rules"):
            feedback += ". Remove those; only say what the original says"
        if why.startswith("lost the order"):
            keep = keep or [s for s in re.split(r"(?<=[.!?])\s+", text)
                            if re.search(r"\b(first|before|later|for now|currently|eventually|future|initially)\b", s, re.I)]
        if keep:
            # say clearly that the WHOLE original must be compressed again (not just these sentences)
            feedback += (". Compress the whole original again. Your new version must still include the meaning of: "
                         + " ".join(f'"{k}"' for k in keep))
    return None


def compress_in_chunks(text):
    """Shorten a long prompt a few sentences at a time. Headings, tables and code blocks are
    kept as they are, list markers ("- ", "1. ") stay in place, and chunks the AI can't shorten
    safely stay exactly as written -- so one mistake never costs the whole saving.
    Big prompts use fast mode: bigger chunks, tiny pieces skipped, no retries, parallel requests."""
    big = count_tokens(text) >= BIG_PROMPT
    size, min_tokens = (BIG_CHUNK_SIZE, BIG_MIN_CHUNK) if big else (CHUNK_SIZE, 8)
    chunks = split_chunks(text, size)
    work = [i for i, (chunk, _) in enumerate(chunks)
            if count_tokens(chunk) > min_tokens and not STRUCTURE_LINE.match(chunk)
            and count_tokens(chunk) <= MAX_AI_TOKENS]
    mode = f", fast mode, {PARALLEL} at a time" if big else ""
    print(f"  [3 AI       ] long prompt: shortening {len(work)} of {len(chunks)} chunks separately{mode}")
    out = [chunk + gap for chunk, gap in chunks]
    start = time.perf_counter()

    def shorten(i):
        chunk, gap = chunks[i]
        prefix = LIST_PREFIX.match(chunk)
        prefix = prefix.group(0) if prefix else ""
        short = compress(chunk[len(prefix):], "3 AI", verbose=False,
                         min_overlap=CHUNK_MIN_OVERLAP, retry=not big)
        return i, chunk, gap, prefix, short

    workers = PARALLEL if big else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(shorten, i) for i in work]
        for n, future in enumerate(as_completed(futures), 1):
            i, chunk, gap, prefix, short = future.result()
            elapsed = time.perf_counter() - start
            eta = elapsed / n * (len(work) - n)
            timing = f"  ({elapsed:.0f}s, ~{eta:.0f}s left)" if len(work) > 3 else ""
            label = f"3 AI {n}/{len(work)}"
            if short:
                print(f"  [{label:<11}] {count_tokens(chunk):>3} → {count_tokens(prefix + short):>3} tokens ✅{timing}")
                out[i] = prefix + short + gap
            else:
                print(f"  [{label:<11}] {count_tokens(chunk):>3} tokens, kept as is (no safe shorter version){timing}")
    joined = "".join(out).strip()
    # final check on the whole result (numbers, quotes, language, rules across chunks)
    ok, why = compression_is_safe(text, joined, CHUNK_MIN_OVERLAP)
    if not ok:
        print(f"  [3 AI       ] joined result rejected: {why}, keeping the rules version")
        return text
    show("3 AI joined", joined)
    return joined


def spell_one(text, verbose=True):
    """Fix the spelling of one piece of text: the small model first, then the main model
    if the small model's answer is rejected. Returns the fixed text, or None."""
    for model in dict.fromkeys([SPELL_MODEL, MODEL]):
        label = "1 spell" if model == SPELL_MODEL else "1 spell 4b"
        try:
            fixed, secs = spell_fix(text, model)
        except Exception as e:
            print(f"  [{label:<11}] skipped: {e}")        # e.g. Ollama isn't running, or output cut off
            if isinstance(e, (ConnectionError, OSError)):
                return None                             # no point trying another model
            continue
        ok, why = spelling_is_safe(text, fixed)
        if ok:
            remember_spell(text, fixed, model)          # only accepted answers are cached
            fixed = restore_quote_style(text, fixed)
            if verbose:
                show(label + " " + (f"{secs:.1f}s" if secs else "cache"), fixed)
            return fixed
        forget_spell(text, model)                       # a bad cached answer gets retried next time
        if verbose:
            print(f"  [{label:<11}] rejected: {why}")
    return None


def spell_step(text):
    """Step 1. Short prompts are fixed in one call; long prompts chunk by chunk,
    and only the chunks that actually contain typos are sent to the model."""
    if count_tokens(text) <= CHUNK_ABOVE:
        if not needs_spell_fix(text):
            print("  [1 spell    ] skipped: no typos found")
            return text
        return spell_one(text) or text
    chunks = split_chunks(text, SPELL_CHUNK_SIZE)
    todo = [i for i, (chunk, _) in enumerate(chunks)
            if chunk.strip() and not STRUCTURE_LINE.match(chunk) and needs_spell_fix(chunk)]
    if not todo:
        print("  [1 spell    ] skipped: no typos found")
        return text
    print(f"  [1 spell    ] {len(todo)} of {len(chunks)} chunks have typos")
    out = [chunk + gap for chunk, gap in chunks]
    fixed_count = 0
    for i in todo:
        chunk, gap = chunks[i]
        fixed = spell_one(chunk, verbose=False)
        if fixed:
            out[i] = fixed + gap
            fixed_count += 1
    print(f"  [1 spell    ] fixed {fixed_count} of {len(todo)} chunks")
    result = "".join(out)
    if result != text:
        show("1 spell", result)
    return result


def report(prompt, final):
    before_score, before_details = rate(prompt)
    after_score, details = rate(final)
    before_tokens = count_tokens(prompt)
    after_tokens = count_tokens(final)
    saved = before_tokens - after_tokens

    b_cost, b_quality = split_scores(before_details)
    a_cost, a_quality = split_scores(details)

    def preview(text, limit=3000):
        if len(text) <= limit:
            return text
        return text[:2000] + f"\n   [... {len(text) - 2500} more characters ...]\n" + text[-500:]
    print("\n" + "=" * 50)
    print("ORIGINAL :", preview(prompt))
    print("OPTIMIZED:", preview(final))
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


def optimize_file(in_path, out_path=None):
    """Optimize the prompt in a text file and save the result. Returns the output path."""
    in_path = Path(in_path)
    prompt = in_path.read_text(encoding="utf-8").strip()
    if not prompt:
        print("Empty prompt.")
        return None
    started = time.perf_counter()
    rules_version, final = pipeline(prompt)
    report(prompt, final)
    out_path = Path(out_path) if out_path else in_path.with_name(in_path.stem + ".optimized" + in_path.suffix)
    out_path.write_text(final + "\n", encoding="utf-8")
    print(f"\nSaved the optimized prompt to {out_path}  (took {time.perf_counter() - started:.0f}s)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize a prompt to use fewer tokens.")
    parser.add_argument("--file", "-f", help="read the prompt from this text file")
    parser.add_argument("--out", "-o", help="where to save the result (default: <file>.optimized.txt)")
    parser.add_argument("--no-ai", action="store_true", help="rules only: instant, no Ollama needed")
    args = parser.parse_args()
    if args.no_ai:
        USE_AI = False
    try:
        if args.file:
            optimize_file(args.file, args.out)
            sys.exit()
        prompt = read_prompt()
        if not prompt:
            print("Empty prompt.")
            sys.exit()
        rules_version, final = pipeline(prompt)
        report(prompt, final)
        if args.out:
            Path(args.out).write_text(final + "\n", encoding="utf-8")
            print(f"\nSaved the optimized prompt to {args.out}")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(1)
