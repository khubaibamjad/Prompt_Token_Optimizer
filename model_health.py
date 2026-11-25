"""Check the health and speed of the local Ollama models.

Usage:
    py model_health.py                         # checks the models used by the optimizer
    py model_health.py gemma3:1b gemma3:4b     # compare specific models
"""
import sys
import time
import ollama
from llm_optimizer import client, MODEL, SPELL_MODEL, SPELL_SYSTEM

TEST_PROMPT = "hi how r u doig ? please help me to rite method for ary revrsal ? can u do dat ?"
RUNS = 3


def get(obj, key, default=None):
    """Read a field from an Ollama response, whether it's an object or a dict."""
    value = getattr(obj, key, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(key)
    if value is None:
        try:
            value = obj[key]
        except Exception:
            value = None
    return default if value is None else value


def gb(n_bytes):
    return f"{n_bytes / 1e9:.1f} GB"


# ---------- 1. is Ollama running? ----------
def check_server():
    print("1. Ollama server")
    try:
        models = get(client.list(), "models", [])
    except Exception as e:
        print(f"   ❌ Not reachable: {e}")
        print("   Start the Ollama app (llama icon in the tray) and try again.")
        sys.exit(1)
    print(f"   ✅ Running. {len(models)} model(s) downloaded:")
    names = []
    for m in models:
        name = get(m, "model") or get(m, "name")
        names.append(name)
        print(f"      - {name:<20} {gb(get(m, 'size', 0))}")
    return names


# ---------- 2. model details ----------
def check_model(name):
    info = client.show(name)
    details = get(info, "details", {})
    modelinfo = get(info, "modelinfo", {}) or {}
    context = next((v for k, v in modelinfo.items() if k.endswith("context_length")), "?")
    print(f"   family: {get(details, 'family', '?')}, "
          f"parameters: {get(details, 'parameter_size', '?')}, "
          f"quantization: {get(details, 'quantization_level', '?')}, "
          f"max context: {context}")


# ---------- 3. speed test ----------
def benchmark(name):
    results = []
    for i in range(RUNS):
        start = time.perf_counter()
        r = client.chat(
            model=name,
            messages=[{"role": "system", "content": SPELL_SYSTEM},
                      {"role": "user", "content": f"Original: {TEST_PROMPT}\nOutput:"}],
            options={"temperature": 0, "num_predict": 200, "num_ctx": 2048},
            keep_alive="30m",
        )
        wall = time.perf_counter() - start
        ns = 1e9
        load = get(r, "load_duration", 0) / ns
        p_tok, p_time = get(r, "prompt_eval_count", 0), get(r, "prompt_eval_duration", 0) / ns
        e_tok, e_time = get(r, "eval_count", 0), get(r, "eval_duration", 0) / ns
        results.append(wall)
        print(f"   run {i + 1}: {wall:5.1f}s total | load {load:4.1f}s | "
              f"read {p_tok} tok @ {p_tok / p_time if p_time else 0:5.1f} tok/s | "
              f"write {e_tok} tok @ {e_tok / e_time if e_time else 0:5.1f} tok/s")
    reply = r["message"]["content"].strip().replace("\n", " ")
    print(f"   output: {reply[:120]}")
    return min(results), e_tok / e_time if e_time else 0


# ---------- 4. what's loaded, and on CPU or GPU? ----------
def check_loaded():
    print("\n4. Loaded models (ollama ps)")
    loaded = get(client.ps(), "models", [])
    if not loaded:
        print("   none loaded")
    for m in loaded:
        size, vram = get(m, "size", 0), get(m, "size_vram", 0)
        gpu = 100 * vram / size if size else 0
        where = "100% CPU" if gpu == 0 else f"{gpu:.0f}% GPU / {100 - gpu:.0f}% CPU"
        print(f"   {get(m, 'model') or get(m, 'name')}: {gb(size)} in memory, {where}, "
              f"stays loaded until {get(m, 'expires_at', '?')}")


def verdict(speed):
    if speed >= 15:
        return "✅ fast"
    if speed >= 6:
        return "🟡 ok"
    return "🔴 slow: try a smaller model"


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(dict.fromkeys([SPELL_MODEL, MODEL]))
    downloaded = check_server()

    summary = []
    for name in wanted:
        print(f"\n2-3. {name}")
        if not any(d == name or d.startswith(name + ":") for d in downloaded):
            print(f"   ❌ not downloaded. Run: ollama pull {name}")
            continue
        try:
            check_model(name)
            best, speed = benchmark(name)
            summary.append((name, best, speed))
        except ollama.ResponseError as e:
            print(f"   ❌ error: {e}")

    check_loaded()

    if summary:
        print("\n5. Summary (best of", RUNS, "runs)")
        for name, best, speed in summary:
            print(f"   {name:<20} {best:5.1f}s per spell fix | writes {speed:5.1f} tok/s  {verdict(speed)}")
