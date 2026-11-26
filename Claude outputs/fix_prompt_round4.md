# Prompt: Round 4 fixes for my Prompt Token Optimizer

You are a senior Python engineer working on my prompt optimizer (`optimizer.py`, `main.py`, `llm_optimizer.py`, `tests.py`). The last round added chunking, retries, parallel calls and `--file` mode. Those work well. However, **none of the round 3 fixes were applied**, and an independent test found 2 new issues. Right now 219 of 220 tests pass.

Fix **only** the items below. Do not add new features this round.

## Rules
1. Keep every existing test passing. Do not delete or weaken any test.
2. Add every input below to `tests.py` as a regression test, with the exact expected result. Test the safety checks with fake model outputs (no Ollama).
3. When the code can't tell whether a change keeps the meaning, leave the text unchanged or reject the AI output. A missed saving is fine; a changed meaning is not.
4. When you're done, show:
   - the diff for each file
   - one line per fix explaining the cause
   - the full output of `py tests.py`
   - a table listing **every test case in this prompt** with PASS/FAIL

---

## 1. Spell step accepts lost content and swapped words (critical)
`spelling_is_safe(original, fixed)` must return:

| original | fixed | expected | now |
|---|---|---|---|
| `Write a short story about a lost puppy finding its way home. Keep it under 300 words, use simple language for young children and end with a happy reunion.` | the same, minus ` and end with a happy reunion` | **False** | True ❌ |
| `Write an email to my professor asking for a deadline extension on my thesis, keep it formal and apologetic, and mention my medical appointment.` | the same, minus `, and mention my medical appointment` | **False** | True ❌ |
| `Write a review of the movie and make it positive and enthusiastic for my blog readers.` | `…make it negative and harsh…` | **False** | True ❌ |
| `bhai mere live aik msg leik do ke mein kal nai aa skta` | `bhai mere liye aik msg likh do ke main kal nahi aa sakta` | **True** | False ❌ (this is the example in `SPELL_SYSTEM` itself) |
| `can u hlp me rite a leter to my boss abt my sallary incrase` | `can you help me write a letter to my boss about my salary increase` | True | True ✅ keep |
| `wat is capitl of frane` | `The capital of France is Paris.` | False | False ✅ keep |

**Fix direction:** align the original and fixed text word by word with `difflib.SequenceMatcher` over the word lists.
- `equal` blocks are fine.
- In `replace` blocks, each old→new word pair must be similar (`SequenceMatcher(None, old, new).ratio() >= 0.5`) or a known slang expansion (`u→you`, `r→are`, `ur→your`, `abt→about`, `msg→message`, `dat→that`). So `positive→negative` fails and `leik→likh`, `live→liye` and `skta→sakta` pass.
- In `delete` blocks, only allow removing a repeat of the previous word (`hi hi`). Deleting 2 or more real words fails.
- `insert` blocks of more than 2 words fail (the model answered or added content).

## 2. Final output is never checked against the original prompt (critical)
Steps 2 and 3 only compare against the text from the step before, so content the spell step dropped is never caught. In `main.pipeline`, after step 3:
- Compare `final` with `pre_clean(prompt)` using `lost_constraints`, `lost_requests`, `missing_protected` and `changed_language`.
- If any check fails, print why and fall back to `optimize(pre_clean(prompt))` (the rules-only version, without the spell fix).
- Do the same for `--file` mode.

Test: mock `spell_fix` to drop `and end with a happy reunion` (as in item 1) and turn off the item 1 check (or make the mock bypass it). The final output must still contain `happy reunion`.

## 3. A rule or request with two subjects can lose one
`compression_is_safe(before, after)` must return:

| before | after | expected | now |
|---|---|---|---|
| `Write a detailed product launch announcement for our new wireless headphones aimed at college students, highlighting battery life, comfort, noise cancellation and the student discount. Do not mention the price or competitor brands.` | same, ending `Do not mention the price.` | **False** | True ❌ |
| `Write a story about a dragon and also include a map of the kingdom.` | `Write a story about a dragon in a kingdom.` | **False** | True ❌ |
| `Do not include any examples or code. Explain recursion.` | `Explain recursion. No examples, no code.` | **True** | False ❌ (new bug: `added_constraints` says "no code" was added) |
| `Create a 7 day meal plan for a vegetarian who does not eat eggs and wants high protein.` | `Create a 7-day high-protein vegetarian meal plan, no eggs.` | True | True ✅ keep |
| `Write a Python function that sorts a list of dictionaries by the age key and never modifies the original list.` | `…without modifying the original list.` | True | True ✅ keep |

**Fix direction:**
- **Negations** in `lost_constraints`: split the words after the negation on `or`, `and`, `nor` and `,` into subjects (`price` | `competitor brands`). *Each* subject must survive with a negation within ~4 words before it.
- **Requests** in `lost_requests`: after `and`, `also` or `plus`, skip an optional verb and take the first noun (`include a MAP` → `map`). That noun must survive.
- **`added_constraints`**: a negated word in the rewrite counts as already in the original if that word appears anywhere in the original's negation scope, which runs from the negation word to the end of its clause or sentence, not just 4 words. So `do not include any examples or code` covers `no code`.

## 4. "Can you <verb>" turns questions into commands
`optimize(pre_clean(x))` must give:

| input | expected | now |
|---|---|---|
| `Can you use a VPN to watch Netflix abroad?` | **unchanged** | `Use a VPN…?` ❌ |
| `Can you read Japanese?` | **unchanged** | `Read Japanese?` ❌ |
| `Could you go faster than light in theory?` | **unchanged** | `Go faster…?` ❌ |
| `Can you do that in Python? Write a sort function.` | **unchanged** | `Do that in Python?…` ❌ |
| `Can you find the bug in this code?` | `Find the bug in this code.` | `…code?` ❌ |
| `Can you help me understand recursion?` | `Help me understand recursion.` | `…recursion?` ❌ |
| `Can you swim?` | unchanged | ✅ keep |

**Fix direction:** only rewrite when the verb is in a short list of task verbs: `write, explain, summarize, summarise, translate, fix, create, generate, list, draft, rewrite, review, find, check, describe, compare, help (only when followed by "me")`. Never rewrite ability or possibility verbs: `use, read, go, do, see, hear, speak, run, swim, eat, drive`. When you do rewrite, change the sentence's final `?` to `.`.

## 5. Small-talk rule eats real phrases
| input | expected | now |
|---|---|---|
| `I want to know how you, as an AI, make decisions.` | **unchanged** | `I want to know as an AI, make decisions.` ❌ |
| `Describe how you all work together as a team.` | **unchanged** | `Describe work together as a team.` ❌ |
| `how you doing boi, write a joke` | `Write a joke` | ✅ keep |
| `hi how are you doing? please help me to write method for array reversal? can you do that?` | (existing test) | ✅ keep |

**Fix direction:** only remove `how you`, `how are you` or `how r u` (+ doing/today) at the very start of the text, right after a greeting, or as a whole sentence of its own. Never remove it when another word comes right before `how` in the same sentence. After `how you`, don't count `all`, `team`, `there` or `everyone` as address words.

## 6. Greeting + address word that is really the topic
| input | expected | now |
|---|---|---|
| `Hey boy names starting with A` | **unchanged** | `Names starting with A` ❌ |
| `Hey there Delilah song meaning` | **unchanged** | `Delilah song meaning` ❌ |
| `Hey dude where is my car movie review` | **unchanged** | `Where is my car movie review` ❌ |
| `Dear friend letter template` | **unchanged** | `Letter template` ❌ |
| `hii heyy helo hello write a haiku` | `Write a haiku` | `Hello write a haiku` ❌ |
| `Hi friend, write a poem` | `Write a poem` | ✅ keep |
| `Hello team, please share the report.` | `Share the report.` | ✅ keep |

**Fix direction:** remove "greeting (+ address word)" only when it's followed by punctuation (`, ! .`), a newline, small talk (`how are you…`), another greeting, or a request (a request verb, `please`, `can you`). Otherwise leave the whole text unchanged.

## 7. Chunk mode sends unfenced code to the AI (new)
`split_chunks` and `STRUCTURE_LINE` only skip lines starting with `#`, `|`, a code fence or `<`. Indented code or YAML pasted **without** fences is sent to the AI as prose, and changes get accepted:
- Input (over 80 tokens, so chunk mode runs): a request sentence, then
  ```
  def compute(items):
      total_price_with_discount = sum(item.price for item in items if item.active)
      return total_price_with_discount
  ```
  then a closing rule sentence. A model that rewrites the line to `sum(i.price for i in items if i.active)` is **accepted**.

Expected: code lines are never sent to the AI and never changed. Treat these as structure (skip them in both the spell and compress chunking):
- lines indented by 4+ spaces or a tab
- lines matching `^\s*(def|class|import|from|return|if|for|while|function|const|let|var|public|private)\b`
- lines ending in `:` `{` `}` `;` or `)`
- `key: value` lines that follow a line ending in `:` (YAML)

Add a test with a mock that changes code and assert the code line is byte-for-byte unchanged.

## 8. Check one test with the real tokenizer
`R2-1 good compression accepted (Avoid using jargon…)` fails with "not shorter" when token counts are only approximate (12 words vs 16, same approximate token count). Run it with real tiktoken and report the two token counts. If the rewrite really isn't shorter in tokens, replace the test's `after` with a shorter rewrite. Don't loosen the "shorter" check.

---

## Already working (don't break these)
- Chunk mode on `examples/marketplace_spec.md`: a safe shortener gives 1081 → ~820 tokens, and chunks with dropped sentences are all rejected and kept as they were.
- Chunks where the model removed negations are rejected.
- Parallel cache writes: 3 threads × 300 writes, no errors.
- Flipped negations, dropped "limerick", lost number "5", Urdu → "cake recipe" and dropped "formal" are all still rejected.

## Final checklist
- [ ] Every row marked ❌ above now gives the expected result.
- [ ] Every row marked ✅ still passes.
- [ ] The final output is checked against the original prompt.
- [ ] Unfenced code and YAML are never sent to the AI.
- [ ] `py tests.py` is fully green, and the PASS/FAIL table is included.
