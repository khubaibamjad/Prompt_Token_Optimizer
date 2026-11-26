# Prompt: Round 3 fixes for my Prompt Token Optimizer

You are a senior Python engineer working on my prompt optimizer (`optimizer.py`, `main.py`, `llm_optimizer.py`, `tests.py`). Right now 153 of 154 tests pass. An independent test run found the issues below. Some are left over from the last round and some came in with the newest changes: the "can you …" rule, greeting typos, the 4b retry for spelling, and `kept_correct_words`. Fix only these.

## Rules
1. Keep every existing test passing. Do not delete or weaken any test.
2. Add a regression test for each item. Use the inputs below as tests, and test safety checks with fake model outputs (no Ollama).
3. When the code can't tell whether a change keeps the meaning, leave the text unchanged or reject the AI output. A missed saving is fine; a changed meaning is not.
4. When you're done, show:
   - the diff for each file
   - one line per fix explaining the cause
   - the output of `py tests.py`

---

## 1. Spell step accepts lost content and changed meaning (critical, new)
The spell check was loosened (word ratio 0.7, keeping 75% of the correctly spelled words). Now a spell "fix" can drop a whole clause or flip a word, and the loss is **never caught later**, because step 3 compares the compressed text with the already-damaged `rules_version`.

`spelling_is_safe(original, fixed)` must return **False** for these:

| original | fixed | currently |
|---|---|---|
| `Write a short story about a lost puppy finding its way home. Keep it under 300 words, use simple language for young children and end with a happy reunion.` | the same, minus `and end with a happy reunion` | accepted |
| `Write an email to my professor asking for a deadline extension on my thesis, keep it formal and apologetic, and mention my medical appointment.` | the same, minus `and mention my medical appointment` | accepted |
| `Write a review of the movie and make it positive and enthusiastic for my blog readers.` | `…make it negative and harsh…` | accepted |

…and must return **True** for these:

| original | fixed | currently |
|---|---|---|
| `can u hlp me rite a leter to my boss abt my sallary incrase` | `can you help me write a letter to my boss about my salary increase` | accepted, keep it |
| `bhai mere live aik msg leik do ke mein kal nai aa skta` | `bhai mere liye aik msg likh do ke main kal nahi aa sakta` | **rejected**, though this is the example in `SPELL_SYSTEM` itself |

And it must still return **False** for `wat is capitl of frane` → `The capital of France is Paris.`

**Fix direction:**
- A spelling fix should be a word-by-word alignment. Use `difflib.SequenceMatcher` on the word lists of the original and the fixed text:
  - Every *correctly spelled* original word (one in the speller dictionary, plus the Roman Urdu words list) must appear in the fixed text, so require about 95% kept, not 75%.
  - Replaced words should be similar to the originals (`difflib.SequenceMatcher(None, a, b).ratio() >= 0.5`, or a known slang expansion like `u→you`, `r→are`, `abt→about`), so `positive→negative` fails.
  - Words that are deleted and not replaced (beyond merging repeats like `hi hi`) should fail.
- Roman Urdu: treat words that aren't in the English dictionary as "unknown" (they may be typos) and accept a fix when it is similar to the original word, so `live→liye`, `leik→likh`, `mein→main`, `nai→nahi`, `skta→sakta` pass.
- **Safety net:** in `main.pipeline`, also run `lost_constraints`, `lost_requests` and `keyword_overlap` for the **final** output against the **pre-cleaned original prompt**, not only against `rules_version`. If they fail, fall back to the rules-only version of the original prompt (without the spell fix).

## 2. Rules that drop half of a two-subject rule or request (left over)
`lost_constraints` and `lost_requests` pass when *any one* content word survives, so the second of two subjects can be dropped. `compression_is_safe` must return **False** for:
- `Write a detailed product launch announcement for our new wireless headphones aimed at college students, highlighting battery life, comfort, noise cancellation and the student discount. Do not mention the price or competitor brands.` → the same text ending in `Do not mention the price.` (the competitor rule is lost; currently **accepted**)
- `Write a story about a dragon and also include a map of the kingdom.` → `Write a story about a dragon in a kingdom.` (the map request is lost; currently **accepted**, because `kingdom` survives)

**Fix direction:**
- **Negations:** split the text after a negation on `or`, `and`, `nor` and `,` into separate subjects (`price`, `competitor brands`). Each subject's main noun must survive with a negation within about 4 words before it. `without`, `no`, `avoid` and `never` count as negations.
- **Requests:** after `and`, `also` or `plus`, find the first noun after an optional verb (`include a MAP`, `a LIMERICK`). That specific noun must survive, not just any word in the window.
- These good compressions must still be **accepted**:
  - `Do not include any examples or code. Explain recursion.` → `Explain recursion. No examples, no code.`
  - `Create a 7 day meal plan for a vegetarian who does not eat eggs and wants high protein.` → `Create a 7-day high-protein vegetarian meal plan, no eggs.`
  - `Write a Python function that sorts a list of dictionaries by the age key and never modifies the original list.` → `Write a Python function to sort a list of dicts by age without modifying the original list.`

## 3. The new "can you <verb>" rule turns questions into commands (new)
- `Can you use a VPN to watch Netflix abroad?` → `Use a VPN to watch Netflix abroad?` (a question about whether it's possible becomes an instruction)
- `Can you read Japanese?` → `Read Japanese?` (a question about the AI's ability)
- `Could you go faster than light in theory?` → `Go faster than light in theory?`
- `Can you do that in Python? Write a sort function.` → `Do that in Python? Write a sort function.`

Expected: all of these stay **unchanged**. Only rewrite "can/could/would you" when:
- the verb is a clear *task* verb (`write, explain, summarize, translate, fix, create, generate, list, draft, rewrite, review, find … in/for me`), not an ability or possibility verb (`use, read, go, do, see, hear, speak, run, swim, help`, where `help me` is fine), **and**
- the result reads as a request: keep the `?` only if the original sentence is a request, or turn the trailing `?` into `.` when you rewrite it (`Can you find the bug in this code?` → `Find the bug in this code.`).

`Can you help me understand recursion?` → `Help me understand recursion.` is fine.

## 4. Small-talk rule eats real phrases (new)
The new `how ((are|r) )?(you|u)` pattern plus address words removes real content:
- `I want to know how you, as an AI, make decisions.` → `I want to know as an AI, make decisions.` → **unchanged**
- `Describe how you all work together as a team.` → `Describe work together as a team.` → **unchanged**

Expected: only remove `how you doing` / `how are you` / `how r u` when it's a separate sentence, at the start of the text, or right after a greeting, never in the middle of a sentence after another word (`know how you`, `describe how you`). Don't treat `all`, `team`, `there` or `everyone` as address words after `how you`.

## 5. Greeting + address word that is really the topic (new)
- `Hey boy names starting with A` → `Names starting with A`
- `Hey there Delilah song meaning` → `Delilah song meaning`
- `Hey dude where is my car movie review` → `Where is my car movie review`
- `Dear friend letter template` → `Letter template`

Expected: all **unchanged**. Only remove "greeting + address word" when it's followed by punctuation (`,` `!` `.`), a newline, small talk, or a clear request (a request verb or `please`/`can you`). `Hi friend, write a poem` → `Write a poem` and `Hello team, please share the report.` → `Share the report.` should still work.

## 6. A run of greetings leaves one behind (minor)
- `hii heyy helo hello write a haiku` → `Hello write a haiku` → **expected** `Write a haiku`. The last greeting before a request verb should go too, using the same rule as in item 5.

## 7. Duplicate model call (minor)
When `gemma3:1b` isn't downloaded, `ask()` already falls back to `MODEL` internally. Then the new retry loop in `main.pipeline` calls `MODEL` *again* for the same prompt. Skip the retry when the first answer actually came from `MODEL`. One way: have `ask()` return the model it used, or remember which models gave a 404.

## 8. Confirm one existing test with the real tokenizer
`R2-1 good compression accepted (Avoid using jargon…)` fails with "not shorter" when token counts are approximate: the rewrite has 12 words vs 16 but the approximate token count is equal. Run it with real tiktoken. If it still fails, the rewrite *is* not shorter in tokens, so either change the test's `after` to a shorter rewrite or make "shorter" compare tokens **or** words. Don't silently loosen the check.

---

## Final checklist
- [ ] Spell step rejects dropped clauses and swapped words; accepts real typo fixes, including Roman Urdu.
- [ ] Final output is checked against the original prompt, not only against `rules_version`.
- [ ] Both subjects of "do not X or Y" and "and also include Z" are checked.
- [ ] "Can you use/read/go…" questions are unchanged; task requests are rewritten without a leftover `?`.
- [ ] `how you`, `Hey boy names`, `Hey there Delilah`, `Dear friend letter template` are unchanged.
- [ ] No duplicate model call when the 1b model is missing.
- [ ] All existing tests pass, plus one new regression test per item.
