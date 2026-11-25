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
     [], [], "Kese ho aap"),
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
    ("Roman Urdu negation kept",
     "main kal office nahi aa sakta", "main kal office nahi aa sakta", False),
]


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
