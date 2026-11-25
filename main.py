from token_counter import count_tokens, compare_models
from optimizer import optimize
from llm_optimizer import llm_optimize
from scorer import rate, grade

USE_AI = True

def pipeline(prompt):
    rules_version=optimize(prompt)
    final=rules_version
    if USE_AI:
        try:
            ai_version = llm_optimize(prompt)
            if count_tokens(ai_version)<count_tokens(rules_version):
                final=ai_version
            else:
                print("(AI rewrite wasn't shorter, keeping the rules version)")
        except Exception as e:
            print(f"(AI step skipped: {e})")   # e.g. Ollama isn't running
    return rules_version, final

def report(prompt, final):
    before_score, _ = rate(prompt)
    after_score, details = rate(final)
    before_tokens = count_tokens(prompt)
    after_tokens = count_tokens(final)
    saved = before_tokens - after_tokens
