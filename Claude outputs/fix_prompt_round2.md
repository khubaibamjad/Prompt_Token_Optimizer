# Prompt: Round 2 fixes for my Prompt Token Optimizer

You are a senior Python engineer. In the last round you fixed my prompt optimizer (`optimizer.py`, `main.py`, `llm_optimizer.py`, `scorer.py`, `token_counter.py`, `tests.py`). All 107 tests pass and the earlier bugs are gone. An independent test run found the remaining issues below. Fix only these. Do not redesign anything or loosen the protections that already work.

## Rules for your work
1. Keep all 107 existing tests passing. Do not weaken or delete any test.
2. Add a regression test for every item below. Test the safety checks with fake model outputs, so they run without Ollama.
3. Make small, targeted changes.
4. When you're done, show:
   - the diff for each file
   - one line per fix explaining the cause
   - the output of `py tests.py`

---

## 1. Main problem: the AI safety checks reject good compressions

`compression_is_safe` now rejects 5 out of 9 correct compressions, so the AI step will rarely be accepted. The cause is that `lost_requests()` and `lost_constraints()` take `words[0]`, the first word longer than 3 letters after "and / also / plus" or after a negation, as the thing that must survive. That word is often a verb or a negation, not the real subject.

**Each of these pairs must be accepted** (call `compression_is_safe(before, after)` and assert it returns `True`):

| before | after | currently rejected because |
|---|---|---|
| `Avoid using jargon or technical terms. Explain how vaccines work to a 10 year old child.` | `Explain how vaccines work to a 10-year-old. Avoid jargon and technical terms.` | lost rule: `avoid using jargon…`. "using" is treated as the subject, and `10` vs `10-year-old` must also count as kept |
| `Could you write a cover letter for a software engineer role and make it sound confident but not arrogant?` | `Write a confident, not arrogant, cover letter for a software engineer role.` | dropped request: `sound` |
| `Write a Python function that sorts a list of dictionaries by the age key and never modifies the original list.` | `Write a Python function to sort a list of dicts by age without modifying the original list.` | dropped request: `never`. A negation word is used as a request word |
| `Create a 7 day meal plan for a vegetarian who does not eat eggs and wants high protein.` | `Create a 7-day high-protein vegetarian meal plan, no eggs.` | dropped request: `wants` |
| `Mujhe ek email likh do apne manager ko ke main kal office nahi aa sakta kyunke meri tabiyat kharab hai` | `Manager ko email likh do ke main kal office nahi aa sakta, tabiyat kharab hai` | keyword overlap 69%, below the 0.7 limit |

**These good compressions already pass. Keep them passing:**
- `Write an email to my landlord about the broken heater and also ask about the rent increase.` → `Email my landlord about the broken heater and ask about the rent increase.`
- `I need you to summarize the following article in 3 bullet points and do not add your opinion.` → `Summarize the article in 3 bullet points. No opinion.`
- `Please explain the difference between TCP and UDP and give one real world example of each.` → `Explain TCP vs UDP with one real-world example of each.`
- `Translate this paragraph into Spanish and keep the tone formal and polite.` → `Translate this paragraph into Spanish, formal and polite tone.`

**These must still be rejected** (they already are; keep it that way):
- `Do not use Python, use Rust to write a web server` → `Use Python, not Rust, to write a web server` (negation flipped)
- `Write a poem about the ocean and also a haiku about mountains and a limerick about cats` → `Write a poem about the ocean and a haiku about mountains.` (dropped request)
- `Write exactly 5 bullet points about tea, max 500 words` → `Write bullet points about tea, max 500 words` (lost number)
- An Urdu-script prompt → `Write a cake recipe` (script changed)
- `Answer only in French and use formal tone. Explain photosynthesis.` → `Explain photosynthesis.`

**Fix direction:**
- In `lost_requests` and `lost_constraints`, skip these words when choosing the subject:
  - negation words (everything in `NEGATIONS`: never, not, no, without…)
  - helper and desire verbs (want, wants, wanted, need, needs, like, sound, seem, look, feel, keep, try, eat, use, using, make, made)
  - words ending in `-ing` when a later content word exists
- Check **all** content words in the window, not just `words[0]`. Accept the result when at least one of the nouns or adjectives survives (by its 5-letter prefix) in the rewrite. For negations, that word must also have a negation within ~4 words before it. Treat `without` as a negation in the rewrite.
- Numbers: count `10` as kept when it appears as `10-year-old`, `7-day` or `16GB`. The current `(?![.,]?\d)` lookahead already allows this; make sure hyphens don't block it.
- Keyword overlap: Roman Urdu and other prompts that drop many small function words should not fail at 0.69. Either skip common Roman Urdu function words (`ek, apne, meri, mera, kyunke, ke, ko, ka, ki, main, hai, do`) when counting key words, or lower the limit to 0.6 when `lost_constraints` and `lost_requests` both found nothing. Pick one and explain why.

## 2. Lowercase sentence start after removing "please"
`remove_please` removes "please" at the start of a sentence but leaves the next word lowercase:
- `he said 'hi' and then left. pls summarize` → `he said 'hi' and then left. summarize` → **expected** `… left. Summarize`
- `write it in python. please also add comments` → `… python. also add comments` → **expected** `… python. Also add comments`
- `It's the students' books and the teachers' pens. please explain` → **expected** `… pens. Explain`
- `Unbalanced quote: "hello world. Please explain.` → **expected** `… world. Explain.`

Fix: capitalize the next word only when "please" was removed from the start of a sentence (after `. ! ?`, a newline, or the start of the text). Use the same safety rules as `capitalize_first`: never change words like `iPhone`, `npm`, paths, URLs or code. Don't capitalize after a comma or semicolon.

## 3. "pls" in the middle of a sentence is no longer removed (regression)
- `krta hun pls plslplsplsplsplpsl leik do na ???????_))(__)()(_(` → now `krta hun pls leik do na?` → **expected** `krta hun leik do na?`

In lowercase, `pls` and `plz` are almost always politeness (the acronym case `PLS` is uppercase and already protected). Remove lowercase `pls` and `plz` anywhere, but keep:
- uppercase `PLS` and `PLZ`
- anything inside quotes or code
- `pls` when it's the subject (`the pls tool`, `pls command`): keep it when it follows `the`, `a` or `an`, or comes before `tool`, `command`, `file`, `package`, `regression` or `method`

Make sure `Explain LSP (language server protocol) and the pls tool` stays **unchanged**.

## 4. Repeated politeness words aren't fully collapsed
- `pls pls pls` → `pls pls` → **expected** `pls` (or, since everything else would be removed, keep the original prompt like the other greeting-only cases do; just be consistent)

`remove_repeated_words` should collapse a repeat of a word in `REPEATABLE` (plus `pls`, `plz` and `thx`) however many times it repeats.

---

## Final checklist
- [ ] All 9 good compressions from section 1 are accepted (the 5 in the table plus the 4 that already pass), and all 5 bad ones are still rejected.
- [ ] Sentence starts are capitalized after removing "please"/"pls", with `iPhone`, `npm`, URLs and code left unchanged.
- [ ] Lowercase mid-sentence `pls`/`plz` is removed; `PLS`, quoted text and `the pls tool` are kept.
- [ ] `pls pls pls` is handled consistently.
- [ ] All existing tests pass, plus one new regression test for each item.
