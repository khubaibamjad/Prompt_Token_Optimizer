# Prompt: Fix bugs in my Prompt Token Optimizer

You are a senior Python engineer. Fix the bugs listed below in my Python project, a prompt optimizer that cuts token usage. Do not rewrite the project or change its design. Make the smallest correct fix for each bug.

## Project files
- `token_counter.py`: tiktoken token counting (`count_tokens`, `compare_models`)
- `optimizer.py`: regex rules (`optimize`, `pre_clean`, `protect`/`restore`, `lost_constraints`, `keyword_overlap`)
- `llm_optimizer.py`: Ollama calls (gemma3:1b spell fix, gemma3:4b compression), `clean()`, JSON cache, `needs_spell_fix`
- `scorer.py`: prompt scoring (`rate`, `score_efficiency`, …)
- `main.py`: pipeline (pre-clean → AI spell fix → rules → AI compression → safety checks → report)
- `tests.py`: test suite (`py tests.py`, `py tests.py --ai`)

## Rules for your work
1. Keep every test in `tests.py` passing. Do not weaken or delete any existing test.
2. For every bug below, add a regression test to `tests.py`. Use the input as the test and the expected result as the assertion. Put rule bugs in `RULE_TESTS` or `CONSTRAINT_TESTS`. Test the AI safety checks (`compression_is_safe`, `spelling_is_safe`, `clean`) directly with fake model outputs, so they run without Ollama.
3. Be conservative. When a rule can't tell whether a word is filler or part of the task, leave the text unchanged. A missed saving is fine; a changed meaning is not.
4. Do not add heavy dependencies. Standard library plus the existing packages (tiktoken, ollama, pyspellchecker) only.
5. When you're done, show:
   - the diff for each file
   - a short note per bug (one line: what caused it and how you fixed it)
   - the output of `py tests.py`

---

## A. Critical bugs (fix first)

**A1. Crash when the optimized prompt is empty.**
`main.py` crashes with `ZeroDivisionError` in `scorer.score_efficiency` (`/ before`) when the input is `hello hello`, `Thanks!`, `please`, `hi` or `pls pls pls`. These optimize to `""`, and then `report()` calls `rate("")`.
Expected: no crash. If the rules remove everything, keep the original prompt as the final one and print a note. Also make `score_efficiency` safe when the token count is 0.

**A2. Placeholder corruption in `protect()`/`restore()`.**
Input `Parse {"a":{"b":{"c":[1]}}} please` produces `Parse {0 1 2:[1`. The placeholder delimiters ``/`` count as symbols (`[^\w\s]`), so `remove_symbol_junk` (and possibly `remove_decorations` and `collapse_punctuation`) eat or split them, and the protected text is lost.
Expected: placeholders can't be touched by any rule. One option is a placeholder made only of word characters that can't appear naturally, e.g. `QXPH0QXPH`, plus a check that it isn't already in the input. Also, an input that already contains `…` currently crashes `restore()` with `IndexError`. It must not crash. `restore()` must never fail silently either: if a placeholder is missing after the rules run, fall back to the original text.

**A3. `main.py` stops reading at the first blank line.**
The input loop ends on `""`, so a prompt with more than one paragraph is cut off after its first paragraph. Piping a prompt in without a trailing blank line crashes with `EOFError`.
Expected: read until EOF (`sys.stdin.read()`) or until a clear end marker such as a line containing only `END`, and print how to finish the input. Handle `EOFError` and `KeyboardInterrupt` cleanly.

**A4. Long prompts are cut short by the AI.**
`num_predict: 200` caps the model's output, so a long prompt comes back cut short. The spell check only requires a length ratio of at least 0.6, so a prompt cut from 420 to 261 tokens (62%) is accepted. `num_ctx: 2048` can also cut the input on Ollama's side, which drops the system instructions.
Expected:
- Set `num_predict` from the input length (for example `count_tokens(prompt) * 2 + 50`), and set `num_ctx` big enough for the system prompt, the user prompt and the output.
- Reject cut-off output: Ollama reports `done_reason == "length"`, and a `<prompt>` tag with no closing tag also means the output was cut off.
- For the spell step, require a length ratio of about 0.85–1.3.
- Above a size limit, skip the AI steps instead of cutting the prompt.

**A5. The number check matches substrings.**
In `lost_constraints`, `if num not in after` passes when `5` is gone but `500` is still there (and the same for `1` vs `10`, `2` vs `2024`). Example: `Write exactly 5 bullet points about tea, max 500 words` → `Write bullet points about tea, max 500 words` is accepted.
Expected: compare numbers as whole tokens, e.g. by counting each number in before vs after with `(?<![\d.,])NUM(?![\d.,]*\d)`. Also count how many times each number appears.

**A6. AI changes the meaning and still passes the checks.**
- A flipped negation passes: `Do not use Python, use Rust to write a web server` → `Use Python, not Rust, to write a web server` is accepted.
- A dropped request passes: `Write a poem about the ocean and also a haiku about mountains and a limerick about cats` → `…ocean and a haiku about mountains.` is accepted, because the 40% keyword-overlap limit is far too low.

Expected:
- Raise the minimum keyword overlap for compression to about 0.7.
- Check that each negation's subject still has a negation right before it (within ~4 words), not just a negation somewhere in the text.
- Check that every content word that follows "and / also / plus" in a list of requests survives.

**A7. Non-Latin prompts aren't checked.**
`keyword_overlap` and `lost_constraints` only use `[a-z]`, so they return 1.0 for Urdu, Arabic, Chinese and Hindi prompts. `مہربانی کر کے میرے باس کو ایک ای میل لکھیں…` was replaced by `Write a cake recipe` and accepted.
Expected: use Unicode-aware word matching (`\w` with `re.UNICODE`, or character n-grams for CJK). If the original is mostly non-Latin, either check overlap properly or skip the AI compression step. Also reject output whose script differs from the input (e.g. the input is mostly Arabic-script and the output is mostly Latin).

---

## B. Rules that change the meaning (`optimizer.py`)

Each line is `input` → current output → **expected**.

1. Single-quoted text isn't protected. Add `'…'` to `PROTECTED` without breaking apostrophes in `don't` or `it's`: match only when the `'` is at a word boundary or start of text, with no letter before the opening quote.
   - `Translate 'please' and 'thank you' into French.` → `Translate '' and …` → **unchanged**
   - `Explain the word 'sss' hissing` → `'ss'` → **unchanged**
2. Greetings are removed even when they're the topic. Only remove a greeting when it's followed by punctuation (`,` `!` `.`) or by an address word like bhai or sir, and something is left afterwards.
   - `Hello World program in Java` → **unchanged**
   - `Hey Jude lyrics meaning` → **unchanged**
   - `Dear Diary format: write an entry` → **unchanged**
   - `hi in Spanish?` → **unchanged**
3. Small talk is removed from real questions. Only remove `how are you` when it's a full sentence (followed by `?`, `.`, `!`, `,` or the end of the text).
   - `How are you different from ChatGPT?` → `Different from ChatGPT?` → **unchanged**
   - `Explain how are you used in English grammar` → **unchanged**
4. Thanks is removed when it's part of the task. Don't remove it when it follows `with`, `say`, `ends`, `note`, `write` or `saying`.
   - `Write an email that ends with thank you` → **unchanged**
5. `" for me"` is removed anywhere. Only remove it right after a request verb (`write/make/create/generate/find … for me`).
   - `Is this plan right for me?` → **unchanged**
6. "Please" is removed when it's the subject, and the please-variants regex `p+l+e*a*s+e*` also deletes `pleas`. Only remove please at the start of a sentence or clause, or right before a verb. Never remove it when it's quoted or used as a verb (`don't please everyone`).
   - `Explain why people say please.` → **unchanged**
   - `Please don't please everyone` → **`Don't please everyone`**
   - `explain the Pleiades and pleas in court` → **unchanged**
7. The keyboard-spam rule deletes real acronyms. Only treat a word as spam when it's 6+ characters long and lowercase, or the same 2–3 letter chunk repeated, and never when it's in capitals.
   - `Explain the PLS regression method` → **unchanged**
   - `Explain LSP` → **unchanged**
   - `slp and lsp and pls and spl and psl` → `And` → **unchanged**
8. `remove_repeated_words` removes intentional repeats. Only collapse repeats of common function words (`the the`, `a a`, `is is`, `to to`), or repeats of 3+ letters when they're clearly typos. Keep capitalized pairs and quoted text.
   - `Plan a trip to Bora Bora` → **unchanged**
   - `Write a song with the chorus no no no no` → **unchanged**
9. Stretched letters break hex values. Skip words that look like hex (`#fff`, `0xfff`, `[0-9a-f]{3,}` near `#` or `0x`) and words in a whitelist (e.g. `zzz`, `sss`, `brrr`, `aaa`, `www`).
   - `Use color #fff and 0xfff` → **unchanged**
   - `aaa battery` → **unchanged**
10. `remove_duplicate_sentences` is too aggressive.
    - Repeated list items and short sentences are deleted: `List 3 fruits. 1. Apple. 2. Banana. 1. Apple.` and `Write a speech. Thanks to all volunteers. Thank you.`
    - Line breaks are merged: `Rules:\nBe short.\nBe kind.\nCite sources.` → one line.
    - Every sentence is capitalized, which breaks `e.g. the Nile` → `e.g. The Nile`, `iPhone` → `IPhone`, `npm` → `Npm` and `www.` → `Www.`.

    Expected:
    - Only remove a sentence that repeats exactly and is 5+ words long.
    - Split and join without losing `\n`.
    - Don't capitalize anything.
    - Remove the final `text[:1].upper()` in `optimize()` too, or skip it when the first word has a capital letter later in it (iPhone) or looks like a command, path or URL.
11. Double period: `Write 500 words. please. Not 500 words more.` → `words.. Not` → **`Write 500 words. Not 500 words more.`**

## C. Formatting and code damage outside backticks (`optimizer.py`)

12. `collapse_whitespace` destroys leading indentation and tabs. It must only collapse runs of spaces *inside* a line. Keep leading whitespace and keep `\t`.
    - `Indented code:\n    def f():\n        return 1` → **unchanged**
    - `name\tage\nali\t30` → **unchanged**
13. Markdown and code symbols are deleted by `remove_decorations` and `remove_symbol_junk`. Keep any line that starts with `#`, any table row (`|…|`), and any line that contains code-like characters (`{}`, `()`, `;`, `=`, `/`, `*` inside words). Only remove decoration lines made of a single repeated character (`-----`, `=====`, `*****`) that stand alone on their own line.
    - `### Step 1` → `Step 1` → **unchanged**
    - table separator `|---|---|` → deleted → **unchanged**
    - `***very bold***` → **unchanged**
    - `Match files **/*.py` → `Match files py` → **unchanged**
    - `Fix <!-- comment --> in HTML` → **unchanged**
    - `explain != and ===` → `===` removed → **unchanged**
    - `my_var___name` → `my_var name` → **unchanged**
14. `collapse_punctuation` removes the space before `.`. Only remove a space before `?!.,` when it's followed by a space or the end of the text, and never shrink `..` or `...`.
    - `Learn .NET and run cd ..` → `Learn.NET … cd.` → **unchanged**
    - `Explain the ellipsis... and what comes next...` → **unchanged**
15. `token_counter.count_tokens` raises `KeyError` for an unknown model (`gpt-3.5`). Fall back to `o200k_base` with a warning, or raise a clear `ValueError`. Also cache the encoding instead of calling `get_encoding` on every call.

## D. AI output handling (`llm_optimizer.py`, `main.py`)

16. Curly quotes always fail. `clean()` turns `“ ”` into `" "`, so any prompt with curly quotes fails `protected_parts` every time. Compare protected parts after normalizing quotes on both sides, and restore the user's original quote style in the final output.
17. `clean()` fallback (when there are no `<prompt>` tags):
    - It keeps only the first paragraph. Keep all of it.
    - The label stripping misses openers like `Sure! Here is the optimized prompt: …`. Strip a leading chatty sentence that ends in `:`.
18. The spell model answers or translates. The cache shows `gemma3:1b` adding a product description to the prompt, and translating Roman Urdu into English. Add a check: if the original is Roman Urdu (common markers: `hai, ho, mujhe, karo, likh, nahi, bhai, ka, ki, ke`) and the output has lost most of those markers, reject it.
19. Rejected AI outputs are cached forever. Only cache outputs that passed the safety checks, or store a `rejected` flag and retry once.
20. `needs_spell_fix` skips capitalized typos (`Halp me` at the start of a sentence). Lowercase the first word of each sentence before checking.

## E. Minor issues
- `model_health.py`: `benchmark` uses `r`, `e_tok` and `e_time` from the last loop iteration only, and breaks if `RUNS == 0`. Report the average and best of all runs.
- `optimizer.py` and `scorer.py` `__main__`: replace `exit()` with `sys.exit()`.
- `scorer.py`: `score_efficiency(prompt)` re-runs `optimize()` on the already optimized prompt, so the "after" score is always about 100. That's fine, but label it in the report as "remaining filler".

## Final checklist
- [ ] All existing `tests.py` tests pass.
- [ ] One new regression test for every item above (A1–A7, B1–B11, C12–C15, D16–D20).
- [ ] `py main.py` works for an empty prompt, a greeting-only prompt, a multi-paragraph prompt, piped input, and input with no Ollama running.
- [ ] No rule changes text inside `"…"`, `'…'`, `“…”`, backticks or fenced code blocks.
