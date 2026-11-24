import re
from token_counter import count_tokens
from optimizer import optimize

CONTEXT_WINDOWS = {"gpt-4": 8192, "gpt-4o": 128000}

STRUCTURE_CHECKS = {
    "task":        r"\b(write|summari[sz]e|explain|list|create|generate|analy[sz]e|translate|fix|compare|classify|extract|rewrite|optimi[sz]e|describe)\b",
    "context":     r"\b(context|background|audience|because|for (a|an|my|the)|about)\b",
    "format":      r"\b(format|bullets?|table|json|markdown|words|sentences|paragraphs?|steps|points)\b",
    "constraints": r"\b(must|only|avoid|don't|do not|limit|maximum|max|at most|under|no more than)\b",
    "example":     r"\b(example|e\.g\.|for instance|such as)\b",
}

VAGUE_WORDS = ["something", "stuff", "things", "etc", "good", "nice", "whatever", "kind of", "sort of", "somehow"]


def score_efficiency(prompt, model):
    """How much of the prompt is waste the optimizer can remove?"""
    before = count_tokens(prompt, model)
    after = count_tokens(optimize(prompt), model)
    waste = (before - after) / before
    return round(100 * (1 - waste)), f"{before - after} of {before} tokens are removable filler"


def score_structure(prompt):
    """Does the prompt contain the parts a good prompt needs?"""
    found = [name for name, pattern in STRUCTURE_CHECKS.items()
             if re.search(pattern, prompt, re.IGNORECASE)]
    missing = [name for name in STRUCTURE_CHECKS if name not in found]
    score = round(100 * len(found) / len(STRUCTURE_CHECKS))
    return score, f"missing: {', '.join(missing) or 'nothing'}"


def score_specificity(prompt):
    """Penalize vague words, reward concrete numbers."""
    text = prompt.lower()
    vague = [w for w in VAGUE_WORDS if re.search(rf"\b{w}\b", text)]
    score = 100 - 20 * len(vague)
    if not re.search(r"\d", text):
        score -= 15        # no numbers like "3 bullets" or "under 100 words"
    return max(0, score), f"vague words: {', '.join(vague) or 'none'}"


def score_budget(prompt, model):
    """Is the prompt a sensible size for the model's context window?"""
    tokens = count_tokens(prompt, model)
    used = tokens / CONTEXT_WINDOWS[model]
    if tokens < 8:
        return 40, f"only {tokens} tokens, likely too little context"
    if used > 0.5:
        return 30, f"uses {used:.0%} of the window, little room left for the answer"
    if used > 0.25:
        return 70, f"uses {used:.0%} of the window"
    return 100, f"uses {used:.2%} of the window"


WEIGHTS = {"efficiency": 0.35, "structure": 0.30, "specificity": 0.20, "budget": 0.15}


def rate(prompt, model="gpt-4o"):
    results = {
        "efficiency":  score_efficiency(prompt, model),
        "structure":   score_structure(prompt),
        "specificity": score_specificity(prompt),
        "budget":      score_budget(prompt, model),
    }
    overall = round(sum(results[k][0] * w for k, w in WEIGHTS.items()))
    return overall, results


def grade(score):
    for limit, letter in [(85, "A"), (70, "B"), (55, "C"), (40, "D")]:
        if score >= limit:
            return letter
    return "F"


if __name__ == "__main__":
    prompt = input("Paste your prompt: ")
    if not prompt.strip():
        print("Empty prompt.")
        exit()

    overall, results = rate(prompt)
    print(f"\nOverall score: {overall}/100  (grade {grade(overall)})\n")
    for name, (score, note) in results.items():
        print(f"{name:<12} {score:>3}/100   {note}")

    print("\nOptimized prompt:", optimize(prompt))