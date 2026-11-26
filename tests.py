"""Automated tests for the prompt optimizer.

    py tests.py          # rule tests only (instant, no AI needed)
    py tests.py --ai     # also runs the full pipeline with the local model (slower)

Run this after every change. If something that used to work breaks, you'll see it here.
"""
import io
import re
import sys
from contextlib import redirect_stdout
from optimizer import optimize, pre_clean

# (name, input, must contain, must NOT contain, exact result or None)
RULE_TESTS = [
    ("quoted title kept",
     'Analyze the lyrics style of the song "Please Please Me" by The Beatles and explain why it was popular.',
     ['"Please Please Me"'], [], None),
    ("filler can't cut inside words",
     "Hi babay how are you doing plz pplease hlp me i luv u",
     ["hlp"], ["phlp", "plz", "pplease", "Hi "], None),
    ("'thank you' as the task is kept",
     "Write a thank you note to my teacher.",
     [], [], "Write a thank you note to my teacher."),
    ("'Hi' inside 'History' is kept",
     "History of Pakistan in 3 points",
     [], [], "History of Pakistan in 3 points"),
    ("URLs and Roman numerals kept",
     "Visit www.google.com and explain III and XXX",
     ["www.google.com", "III", "XXX"], [], None),
    ("command-line flags kept",
     "Use the --verbose flag",
     ["--verbose"], [], None),
    ("words like pleased/plus/pulse kept",
     "I am pleased, the plus sign and pulse rate",
     ["pleased", "plus", "pulse"], [], None),
    ("messy greeting, repeats and symbols",
     "hello hello how are you ??? ...---====",
     [], [], "How are you?"),
    ("closing thanks and Roman Urdu greeting removed",
     "Hello bhai please mujhe ek email likh do apne manager ko, thank you so much",
     ["email", "manager"], ["Hello", "bhai", "thank", "please"], None),
    ("verbose blog prompt keeps the constraints",
     "Hello there! I hope you are doing well today. I would like you to please go ahead and basically "
     "write me a blog post about the benefits of drinking water. It is important to note that the blog post "
     "should be around 500 words. Could you please make sure that it is easy to read? Thank you so much in "
     "advance for your help!",
     ["500 words", "easy to read", "blog post"], ["Hello", "I hope", "Thank", "basically", "go ahead"], None),
    ("small talk kept when it IS the question",
     "kese ho aap",
     [], [], "kese ho aap"),      # was "Kese ho aap": rules no longer capitalize untouched text (B10)
    ("small talk removed when there is a real request",
     "hi how are you doing? please help me to write method for array reversal? can you do that?",
     ["write method", "array reversal"], ["how are you", "can you do that"], None),
    ("Roman Urdu small talk removed",
     "kese ho aap kya haal chaal hai apka mujhe ek email likh do",
     ["email likh do"], ["kese ho", "haal chaal"], None),
    ("symbol junk and keyboard spam removed",
     "krta hun pls plslplsplsplsplpsl leik do na ???????_))(__)()(_(",
     ["leik do"], ["plsl", "(_(", "??"], None),
    ("code inside backticks untouched",
     'Fix `x = a___b ----` and "???!!!" now ?????',
     ["`x = a___b ----`", '"???!!!"'], [], None),
    ("multi-line code block keeps indentation",
     "Can you please fix this:\n```\ndef add(a, b):\n    return a +  b\n```",
     ["    return a +  b"], ["please"], None),
    ("numbers and limits kept",
     "Please write a product description for a laptop with 16GB RAM, 512GB SSD, priced at $899. "
     "It must be under 80 words and must not mention any competitor brands.",
     ["16GB", "512GB", "$899", "under 80 words", "must not mention"], ["Please"], None),
    ("negations kept",
     "Please do not include any examples in your answer. Just explain what recursion is in simple terms, "
     "actually I don't want any code either.",
     ["do not include any examples", "don't want any code"], [], None),
    # ---- regression tests for the bug list (A2, B1-B11, C12-C14) ----
    ('A2 JSON with quoted keys survives',
     'Parse {"a":{"b":{"c":[1]}}} please',
     [], [], 'Parse {"a":{"b":{"c":[1]}}} please'),
    ('B1 single-quoted words protected',
     "Translate 'please' and 'thank you' into French.",
     [], [], "Translate 'please' and 'thank you' into French."),
    ("B1 single-quoted 'sss' protected",
     "Explain the word 'sss' hissing",
     [], [], "Explain the word 'sss' hissing"),
    ("B1 apostrophes aren't treated as quotes",
     "Hello, I don't know what it's for",
     [], [], "I don't know what it's for"),
    ("B2 'Hello World' is a topic",
     'Hello World program in Java',
     [], [], 'Hello World program in Java'),
    ("B2 'Hey Jude' is a topic",
     'Hey Jude lyrics meaning',
     [], [], 'Hey Jude lyrics meaning'),
    ("B2 'Dear Diary' is a topic",
     'Dear Diary format: write an entry',
     [], [], 'Dear Diary format: write an entry'),
    ("B2 'hi' as the topic",
     'hi in Spanish?',
     [], [], 'hi in Spanish?'),
    ("B3 'how are you' inside a question",
     'How are you different from ChatGPT?',
     [], [], 'How are you different from ChatGPT?'),
    ("B3 'how are you' as grammar topic",
     'Explain how are you used in English grammar',
     [], [], 'Explain how are you used in English grammar'),
    ('B4 thanks as part of the task',
     'Write an email that ends with thank you',
     [], [], 'Write an email that ends with thank you'),
    ("B5 'for me' in a real question",
     'Is this plan right for me?',
     [], [], 'Is this plan right for me?'),
    ("B6 'please' as the topic",
     'Explain why people say please.',
     [], [], 'Explain why people say please.'),
    ("B6 'please' as a verb",
     "Please don't please everyone",
     [], [], "Don't please everyone"),
    ("B6 'pleas' and 'Pleiades' kept",
     'explain the Pleiades and pleas in court',
     [], [], 'explain the Pleiades and pleas in court'),
    ('B7 acronym PLS kept',
     'Explain the PLS regression method',
     [], [], 'Explain the PLS regression method'),
    ('B7 acronym LSP kept',
     'Explain LSP',
     [], [], 'Explain LSP'),
    ('B7 short p/l/s words kept',
     'slp and lsp and pls and spl and psl',
     [], [], 'slp and lsp and pls and spl and psl'),
    ("B8 'Bora Bora' kept",
     'Plan a trip to Bora Bora',
     [], [], 'Plan a trip to Bora Bora'),
    ("B8 'no no no no' kept",
     'Write a song with the chorus no no no no',
     [], [], 'Write a song with the chorus no no no no'),
    ('B9 hex colours kept',
     'Use color #fff and 0xfff',
     [], [], 'Use color #fff and 0xfff'),
    ("B9 'aaa battery' kept",
     'aaa battery',
     [], [], 'aaa battery'),
    ('B10 short repeated list items kept',
     'List 3 fruits. 1. Apple. 2. Banana. 1. Apple.',
     [], [], 'List 3 fruits. 1. Apple. 2. Banana. 1. Apple.'),
    ('B10 speech thanks kept',
     'Write a speech. Thanks to all volunteers. Thank you.',
     [], [], 'Write a speech. Thanks to all volunteers. Thank you.'),
    ('B10 line breaks kept',
     'Rules:\nBe short.\nBe kind.\nCite sources.',
     [], [], 'Rules:\nBe short.\nBe kind.\nCite sources.'),
    ('B10 no capitalizing inside sentences',
     'e.g. the Nile and iPhone and npm and www.x.com',
     [], [], 'e.g. the Nile and iPhone and npm and www.x.com'),
    ('B10 iPhone at the start kept',
     'iPhone tips',
     [], [], 'iPhone tips'),
    ('B10 command at the start kept',
     'npm install express',
     [], [], 'npm install express'),
    ('B10 long exact repeat still removed',
     'Summarize this article in three short points. Summarize this article in three short points.',
     [], [], 'Summarize this article in three short points.'),
    ('B11 no double period',
     'Write 500 words. please. Not 500 words more.',
     [], [], 'Write 500 words. Not 500 words more.'),
    ('C12 leading indentation kept',
     'Indented code:\n def f():\n return 1',
     [], [], 'Indented code:\n def f():\n return 1'),
    ('C12 tabs kept',
     'name\tage\nali\t30',
     [], [], 'name\tage\nali\t30'),
    ('C13 markdown heading kept',
     '### Step 1',
     [], [], '### Step 1'),
    ('C13 markdown table kept',
     '| a | b |\n|---|---|\n| 1 | 2 |',
     [], [], '| a | b |\n|---|---|\n| 1 | 2 |'),
    ('C13 bold markers kept',
     '***very bold***',
     [], [], '***very bold***'),
    ('C13 glob pattern kept',
     'Match files **/*.py',
     [], [], 'Match files **/*.py'),
    ('C13 HTML comment kept',
     'Fix <!-- comment --> in HTML',
     [], [], 'Fix <!-- comment --> in HTML'),
    ('C13 operators kept',
     'explain != and ===',
     [], [], 'explain != and ==='),
    ('C13 underscores in names kept',
     'rename my_var___name',
     [], [], 'rename my_var___name'),
    ('C13 standalone divider line removed',
     'Intro\n-----\nText',
     [], [], 'Intro\nText'),
    ('C14 .NET and cd .. kept',
     'Learn .NET and run cd ..',
     [], [], 'Learn .NET and run cd ..'),
    ('C14 ellipsis kept',
     'Explain the ellipsis... and what comes next...',
     [], [], 'Explain the ellipsis... and what comes next...'),
    # ---- round 2 regression tests ----
    ("R2-2 capitalize after removed 'pls' at sentence start",
     "he said 'hi' and then left. pls summarize",
     [], [], "he said 'hi' and then left. Summarize"),
    ("R2-2 capitalize after removed 'please also'",
     'write it in python. please also add comments',
     [], [], 'write it in python. Also add comments'),
    ('R2-2 capitalize after possessive apostrophes',
     "It's the students' books and the teachers' pens. please explain",
     [], [], "It's the students' books and the teachers' pens. Explain"),
    ('R2-2 capitalize after an unbalanced quote',
     'Unbalanced quote: "hello world. Please explain.',
     [], [], 'Unbalanced quote: "hello world. Explain.'),
    ('R2-2 no capital after a comma',
     'Done, please explain',
     [], [], 'Done, explain'),
    ('R2-2 npm stays lowercase after removed please',
     'Fix this. please npm install it',
     [], [], 'Fix this. npm install it'),
    ('R2-2 iPhone unchanged after removed please',
     'Use iPhone. please iPhone tips',
     [], [], 'Use iPhone. iPhone tips'),
    ("R2-3 mid-sentence 'pls' removed",
     'krta hun pls plslplsplsplsplpsl leik do na ???????_))(__)()(_(',
     [], [], 'krta hun leik do na?'),
    ("R2-3 'the pls tool' kept",
     'Explain LSP (language server protocol) and the pls tool',
     [], [], 'Explain LSP (language server protocol) and the pls tool'),
    ("R2-3 'pls command' kept",
     'Run the pls command',
     [], [], 'Run the pls command'),
    ("R2-3 mid-sentence 'plz' removed",
     'can you plz write a poem',
     [], [], 'can you write a poem'),
    ("R2-4 repeated 'pls' fully collapsed before a request",
     'pls pls pls write a poem',
     [], [], 'Write a poem'),
    ("R2-4 repeated 'thx' collapsed, then removed as closing thanks",
     'Write a poem. thx thx thx',
     [], [], 'Write a poem.'),
]

# Known problems we'll fix later: shown as warnings, not failures
KNOWN_ISSUES = [
    ("'...' placeholders kept (test 8)",
     "Write 3 motivational quotes. Format each one like this: Quote: ... Author: ...",
     ["Quote: ...", "Author: ..."], [], None),
]

# (name, input, regexes the FINAL result must match)
AI_TESTS = [
    ("typos fixed, request kept",
     "hi how r u doig ? please help me to rite method for ary revrsal ? ????? can u do dat ?",
     [r"\barray\b", r"revers"]),
    ("quoted title survives the AI",
     'Analyze the lyrics style of the song "Please Please Me" by The Beatles and explain why it was popular.',
     [r'"Please Please Me"', r"Beatles"]),
    ("numbers survive the AI",
     "Please write a product description for a laptop with 16GB RAM, 512GB SSD, priced at $899. "
     "It must be under 80 words and must not mention any competitor brands.",
     [r"16 ?GB", r"512 ?GB", r"\$899", r"80"]),
    ("negations survive the AI",
     "Please do not include any examples in your answer. Just explain what recursion is in simple terms, "
     "actually I don't want any code either.",
     [r"recursion", r"(no|not|n't|without)\b.*example", r"(no|not|n't|without)\b.*code"]),
    ("Roman Urdu stays Roman Urdu",
     "Hello bhai please mujhe ek email likh do apne manager ko ke main kal office nahi aa sakta "
     "kyunke meri tabiyat kharab hai, thank you so much",
     [r"\b(likh|likho|likhna)\b", r"manager"]),
]


# (name, before, after, should it be flagged?)
CONSTRAINT_TESTS = [
    ("dropped 'no examples' is caught",
     "Do not include any examples in your answer. Explain recursion, I don't want any code either.",
     "Explain recursion in simple terms. No code.", True),
    ("both negations kept is fine",
     "Do not include any examples in your answer. Explain recursion, I don't want any code either.",
     "Explain recursion. No examples, no code.", False),
    ("dropped number is caught",
     "Write a 500 word blog post about water.", "Write a blog post about water.", True),
    ("negation flipped to positive is caught",
     "Do not mention competitor brands.", "Mention competitor brands.", True),
    ("spell step: fixed typo after negation is fine",
     "i dont want any kode", "i don't want any code", False),
    ("spell step: dropped negation is caught",
     "i dont want any kode", "i want any code", True),
    ("A5 '5' lost while '500' stays is caught",
     "Write exactly 5 bullet points about tea, max 500 words",
     "Write bullet points about tea, max 500 words", True),
    ("A5 '2' lost while '2024' stays is caught",
     "Give 2 examples from 2024", "Give examples from 2024", True),
    ("A5 a number used twice must stay twice",
     "Write 3 tips, then 3 warnings", "Write 3 tips and warnings", True),
    ("A6 flipped negation (Python/Rust) is caught",
     "Do not use Python, use Rust to write a web server",
     "Use Python, not Rust, to write a web server", True),
    ("R2-1 '10' kept as '10-year-old'",
     "Explain it to a 10 year old child.", "Explain it to a 10-year-old.", False),
    ("R2-1 '7' kept as '7-day', '16' as '16GB'",
     "Create a 7 day plan for a 16 GB laptop", "Create a 7-day plan for a 16GB laptop", False),
    ("R2-1 'avoid USING jargon': jargon is the subject",
     "Avoid using jargon or technical terms.", "Avoid jargon and technical terms.", False),
    ("R2-1 'never modifies' kept as 'without modifying'",
     "Sort the list and never modifies the original list.", "Sort the list without modifying the original list.", False),
    ("Roman Urdu negation kept",
     "main kal office nahi aa sakta", "main kal office nahi aa sakta", False),
]


class FakeResponse(dict):
    """Looks like an Ollama chat response."""
    def __init__(self, content, done_reason="stop"):
        super().__init__(message={"content": content}, done_reason=done_reason)
        self.done_reason = done_reason


class FakeClient:
    """Stands in for Ollama: returns a fixed reply and counts calls."""
    def __init__(self, content, done_reason="stop"):
        self.content, self.done_reason, self.calls = content, done_reason, 0
    def chat(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return FakeResponse(self.content, self.done_reason)


def safety_checks():
    """(name, passed?) for checks on main.py and llm_optimizer.py, using fake model outputs."""
    import llm_optimizer as L
    import main as M
    from optimizer import protect, restore, optimize
    from scorer import rate
    from token_counter import count_tokens

    saved_client, saved_cache, saved_save, saved_ai = L.client, dict(L.CACHE), L.save_cache, M.USE_AI
    L.save_cache = lambda: None                      # never touch the real cache file in tests
    L.CACHE.clear()
    out = []
    def quiet(fn, *args):
        with redirect_stdout(io.StringIO()):
            return fn(*args)
    try:
        # A1: prompts the rules remove completely
        M.USE_AI = False
        for p in ["hello hello", "Thanks!", "please", "hi", "pls pls pls"]:
            _, final = quiet(M.pipeline, p)
            out.append((f"A1 {p!r} keeps a non-empty prompt", final.strip() != ""))
        try:
            rate("")
            out.append(("A1 rate('') doesn't crash", True))
        except ZeroDivisionError:
            out.append(("A1 rate('') doesn't crash", False))

        # A2: placeholders
        text, saved = protect('Keep "x" and QXPH0QXPH literally')
        out.append(("A2 placeholder marker changes if already in text", restore(text, saved) == 'Keep "x" and QXPH0QXPH literally'))
        out.append(("A2 private-use characters don't crash", optimize('a "\ue000b\ue001" c') == 'a "\ue000b\ue001" c'))
        try:
            restore("placeholder gone", saved)
            out.append(("A2 restore() raises when a placeholder is lost", False))
        except ValueError:
            out.append(("A2 restore() raises when a placeholder is lost", True))

        # A3: reading input
        out.append(("A3 multi-paragraph prompt is read fully",
                    M.read_prompt(io.StringIO("Para one.\n\nPara two.\n")) == "Para one.\n\nPara two."))
        out.append(("A3 END marker stops reading",
                    M.read_prompt(io.StringIO("Line 1\nEND\nignored\n")) == "Line 1"))
        out.append(("A3 piped input without trailing newline",
                    M.read_prompt(io.StringIO("no newline at end")) == "no newline at end"))

        # A4: output limits and cut-off output
        long_prompt = "word " * 800
        opts = L.generation_options(L.SPELL_SYSTEM, long_prompt)
        out.append(("A4 num_predict grows with the prompt", opts["num_predict"] >= count_tokens(long_prompt) * 2))
        out.append(("A4 num_ctx fits system + prompt + output",
                    opts["num_ctx"] >= count_tokens(L.SPELL_SYSTEM) + count_tokens(long_prompt) + opts["num_predict"]))
        L.client = FakeClient("<prompt>half of the ans", done_reason="length")
        try:
            L.spell_fix("some prompt to fix")
            out.append(("A4 done_reason=length is rejected", False))
        except L.OutputCutOff:
            out.append(("A4 done_reason=length is rejected", True))
        L.client = FakeClient("<prompt>cut off without a closing tag")
        try:
            L.spell_fix("another prompt to fix")
            out.append(("A4 missing </prompt> is rejected", False))
        except L.OutputCutOff:
            out.append(("A4 missing </prompt> is rejected", True))
        words = [f"item{i}" for i in range(400)]
        ok, _ = M.spelling_is_safe(" ".join(words), " ".join(words[:250]))
        out.append(("A4 spell fix cut to 62% is rejected", not ok))
        L.client = FakeClient("<prompt>should not be called</prompt>")
        M.USE_AI = True
        quiet(M.pipeline, "please explain " + "this topic in detail " * 400)
        out.append(("A4 prompts over MAX_AI_TOKENS skip the AI", L.client.calls == 0))
        M.USE_AI = False

        # A6 / A7: compression must not change the meaning
        ok, _ = M.compression_is_safe("Do not use Python, use Rust to write a web server",
                                      "Use Python, not Rust, to write a web server")
        out.append(("A6 flipped negation is rejected", not ok))
        ok, _ = M.compression_is_safe("Write a poem about the ocean and also a haiku about mountains and a limerick about cats",
                                      "Write a poem about the ocean and a haiku about mountains.")
        out.append(("A6 dropped request is rejected", not ok))
        ok, _ = M.compression_is_safe("Do not include any examples in your answer. Just explain what recursion is in simple terms, I don't want any code either.",
                                      "Explain recursion in simple terms. No examples, no code.")
        out.append(("A6 a good compression is still accepted", ok))
        ok, _ = M.compression_is_safe("مہربانی کر کے میرے باس کو ایک ای میل لکھیں کہ میں کل دفتر نہیں آؤں گا کیونکہ میں بیمار ہوں",
                                      "Write a cake recipe")
        out.append(("A7 Urdu replaced by English is rejected", not ok))
        ok, _ = M.compression_is_safe("请帮我写一封邮件给我的老板，说明我明天因为生病不能来上班",
                                      "写一个蛋糕食谱")
        out.append(("A7 Chinese with unrelated rewrite is rejected", not ok))

        # Round 2, section 1: good compressions must be accepted, bad ones rejected
        good = [
            ("Avoid using jargon or technical terms. Explain how vaccines work to a 10 year old child.",
             "Explain how vaccines work to a 10-year-old. Avoid jargon and technical terms."),
            ("Could you write a cover letter for a software engineer role and make it sound confident but not arrogant?",
             "Write a confident, not arrogant, cover letter for a software engineer role."),
            ("Write a Python function that sorts a list of dictionaries by the age key and never modifies the original list.",
             "Write a Python function to sort a list of dicts by age without modifying the original list."),
            ("Create a 7 day meal plan for a vegetarian who does not eat eggs and wants high protein.",
             "Create a 7-day high-protein vegetarian meal plan, no eggs."),
            ("Mujhe ek email likh do apne manager ko ke main kal office nahi aa sakta kyunke meri tabiyat kharab hai",
             "Manager ko email likh do ke main kal office nahi aa sakta, tabiyat kharab hai"),
            ("Write an email to my landlord about the broken heater and also ask about the rent increase.",
             "Email my landlord about the broken heater and ask about the rent increase."),
            ("I need you to summarize the following article in 3 bullet points and do not add your opinion.",
             "Summarize the article in 3 bullet points. No opinion."),
            ("Please explain the difference between TCP and UDP and give one real world example of each.",
             "Explain TCP vs UDP with one real-world example of each."),
            ("Translate this paragraph into Spanish and keep the tone formal and polite.",
             "Translate this paragraph into Spanish, formal and polite tone."),
        ]
        for before, after in good:
            ok, why = M.compression_is_safe(before, after)
            out.append((f"R2-1 good compression accepted: {before[:45]}..." + ("" if ok else f" ({why})"), ok))
        bad = [
            ("Do not use Python, use Rust to write a web server", "Use Python, not Rust, to write a web server"),
            ("Write a poem about the ocean and also a haiku about mountains and a limerick about cats",
             "Write a poem about the ocean and a haiku about mountains."),
            ("Write exactly 5 bullet points about tea, max 500 words", "Write bullet points about tea, max 500 words"),
            ("مہربانی کر کے میرے باس کو ایک ای میل لکھیں کہ میں کل دفتر نہیں آؤں گا کیونکہ میں بیمار ہوں", "Write a cake recipe"),
            ("Answer only in French and use formal tone. Explain photosynthesis.", "Explain photosynthesis."),
        ]
        for before, after in bad:
            ok, why = M.compression_is_safe(before, after)
            out.append((f"R2-1 bad compression rejected: {before[:45]}...", not ok))

        # Round 2, section 4: 'pls pls pls' is handled like other politeness-only prompts
        out.append(("R2-4 'pls pls pls' alone is removed completely by the rules", optimize("pls pls pls") == ""))
        _, final = quiet(M.pipeline, "pls pls pls")
        out.append(("R2-4 ...so the pipeline keeps the original prompt", final == "pls pls pls"))

        # input: two empty lines end typed input; piped input keeps reading
        out.append(("R2 two empty lines end typed input",
                    quiet(M.read_prompt, io.StringIO("One.\n\nTwo.\n\n\nignored\n"), True) == "One.\n\nTwo."))
        out.append(("R2 piped input reads past two empty lines",
                    M.read_prompt(io.StringIO("One.\n\n\nTwo.\n"), interactive=False) == "One.\n\n\nTwo."))

        # D16: curly quotes
        ok, _ = M.compression_is_safe("Please analyze the song “Let It Be” by The Beatles and explain why it became so popular.",
                                      'Analyze the song "Let It Be" by The Beatles and explain why it became popular.')
        out.append(("D16 curly vs straight quotes count as the same", ok))
        out.append(("D16 the user's curly quotes come back",
                    M.restore_quote_style("Analyze “Let It Be” now", 'Analyze "Let It Be"') == "Analyze “Let It Be”"))

        # D17: clean() without tags
        out.append(("D17 chatty opener removed",
                    L.clean("Sure! Here is the optimized prompt: Write a poem.") == "Write a poem."))
        out.append(("D17 all paragraphs kept",
                    L.clean("Write a poem.\n\nKeep it under 50 words.") == "Write a poem.\n\nKeep it under 50 words."))
        out.append(("D17 a real 'Output format:' line is kept",
                    L.clean("Output format: JSON with two fields") == "Output format: JSON with two fields"))

        # D18: Roman Urdu translated by the spell model
        ok, _ = M.spelling_is_safe("mujhe ek email likh do ke main kal office nahi aa sakta",
                                   "write me an email that I cannot come to the office tomorrow")
        out.append(("D18 Roman Urdu translated to English is rejected", not ok))

        # D19: only accepted answers are cached
        L.client = FakeClient("<prompt>Write a product description for a laptop.</prompt>")
        L.spell_fix("rite a leter")
        out.append(("D19 ask() doesn't cache by itself", L.CACHE == {}))
        L.remember_spell("rite a leter", "write a letter")
        out.append(("D19 accepted answer is cached", L.spell_fix("rite a leter") == ("write a letter", 0.0)))
        L.forget_spell("rite a leter")
        out.append(("D19 rejected answer is removed from the cache", L.CACHE == {}))

        # D20 and C15
        out.append(("D20 capitalized typo at sentence start is found", L.needs_spell_fix("Halp me write a letter.")))
        try:
            count_tokens("hello", "gpt-3.5")
            out.append(("C15 unknown model doesn't crash", True))
        except KeyError:
            out.append(("C15 unknown model doesn't crash", False))
    finally:
        L.client, L.save_cache, M.USE_AI = saved_client, saved_save, saved_ai
        L.CACHE.clear()
        L.CACHE.update(saved_cache)
    return out


def check(result, must, must_not, exact):
    low = result.lower()                       # word checks ignore capitals
    problems = [f"missing {m!r}" for m in must if m.lower() not in low]
    problems += [f"should not contain {m!r}" for m in must_not if m.lower() in low]
    if exact is not None and result != exact:
        problems.append(f"expected {exact!r}")
    return problems


def run_rule_tests():
    failed = 0
    print("RULE TESTS")
    for name, prompt, must, must_not, exact in RULE_TESTS:
        result = optimize(pre_clean(prompt))
        problems = check(result, must, must_not, exact)
        if problems:
            failed += 1
            print(f"  ❌ {name}\n     got: {result!r}\n     " + "\n     ".join(problems))
        else:
            print(f"  ✅ {name}")
    from optimizer import lost_constraints
    for name, before, after, should_flag in CONSTRAINT_TESTS:
        lost = lost_constraints(before, after, check_subjects=not name.startswith("spell step"))
        if bool(lost) != should_flag:
            failed += 1
            print(f"  ❌ {name}\n     lost_constraints returned {lost}")
        else:
            print(f"  ✅ {name}")
    print("\nSAFETY CHECKS (fake model outputs, no Ollama needed)")
    for name, passed in safety_checks():
        if not passed:
            failed += 1
        print(f"  {'✅' if passed else '❌'} {name}")
    print("\nKNOWN ISSUES")
    for name, prompt, must, must_not, exact in KNOWN_ISSUES:
        result = optimize(pre_clean(prompt))
        ok = not check(result, must, must_not, exact)
        print(f"  {'✅' if ok else '⚠️ '} {name}{'' if ok else ' (known issue)'}")
    return failed


def run_ai_tests():
    from main import pipeline
    failed = 0
    print("\nAI PIPELINE TESTS (uses the local model)")
    for name, prompt, patterns in AI_TESTS:
        log = io.StringIO()
        with redirect_stdout(log):                     # hide the step-by-step output
            _, final = pipeline(prompt)
        missing = [p for p in patterns if not re.search(p, final, re.IGNORECASE)]
        if missing:
            failed += 1
            print(f"  ❌ {name}\n     got: {final!r}\n     missing: {missing}")
            print("     steps:\n" + "\n".join("       " + l for l in log.getvalue().strip().splitlines()))
        else:
            print(f"  ✅ {name}  ->  {final}")
    return failed


if __name__ == "__main__":
    failed = run_rule_tests()
    if "--ai" in sys.argv:
        failed += run_ai_tests()
    print(f"\n{'All tests passed ✅' if failed == 0 else f'{failed} test(s) failed ❌'}")
    sys.exit(1 if failed else 0)
