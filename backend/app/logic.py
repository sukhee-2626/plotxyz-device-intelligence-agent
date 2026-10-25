"""Original deterministic implementation for Device Intelligence (plotxyz-device-intelligence-agent)."""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict, deque


class LogicError(ValueError):
    """Raised when supplied input cannot be processed."""


def _text(payload, key, min_len=1, max_len=20000):
    value = payload.get(key)
    if not isinstance(value, str):
        raise LogicError(f"'{key}' must be a string")
    value = value.strip()
    if len(value) < min_len:
        raise LogicError(f"'{key}' is required")
    if len(value) > max_len:
        raise LogicError(f"'{key}' exceeds {max_len} characters")
    return value


def _num(payload, key, default=None, lo=None, hi=None):
    value = payload.get(key, default)
    if value is None or value == "":
        if default is None:
            raise LogicError(f"'{key}' is required")
        return default
    if isinstance(value, bool):
        raise LogicError(f"'{key}' must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise LogicError(f"'{key}' must be numeric")
    if lo is not None and number < lo:
        raise LogicError(f"'{key}' must be at least {lo}")
    if hi is not None and number > hi:
        raise LogicError(f"'{key}' must be at most {hi}")
    return number


def _json(payload, key, expected=None, max_len=200000):
    raw = payload.get(key)
    if isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        if len(raw) > max_len:
            raise LogicError(f"'{key}' exceeds {max_len} characters")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogicError(f"'{key}' is not valid JSON: {exc.msg} at line {exc.lineno}")
    else:
        raise LogicError(f"'{key}' must be JSON")
    if expected is not None and not isinstance(data, expected):
        name = expected.__name__ if hasattr(expected, "__name__") else str(expected)
        raise LogicError(f"'{key}' must be a JSON {name}")
    return data


def _csv(payload, key, max_rows=5000):
    text = _text(payload, key, max_len=2000000)
    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise LogicError(f"'{key}' must include a header row")
        columns = [str(c).strip() for c in reader.fieldnames if c and str(c).strip()]
        if not columns:
            raise LogicError(f"'{key}' must include named columns")
        rows = []
        for index, raw in enumerate(reader):
            if index >= max_rows:
                raise LogicError(f"'{key}' exceeds {max_rows} rows")
            rows.append({col: (raw.get(col) or "").strip() for col in columns})
    except csv.Error as exc:
        raise LogicError(f"'{key}' is not valid CSV: {exc}")
    if not rows:
        raise LogicError(f"'{key}' must include at least one data row")
    return columns, rows


STOPWORDS = {'will', 'they', 'was', 'your', 'than', 'that', 'on', 'be', 'then', 'do', 'our', 'with', 'he', 'is', 'about', 'had', 'were', 'as', 'may', 'we', 'their', 'are', 'did', 'at', 'she', 'a', 'by', 'the', 'if', 'might', 'it', 'into', 'have', 'from', 'should', 'not', 'over', 'can', 'for', 'and', 'an', 'you', 'does', 'to', 'this', 'could', 'would', 'under', 'of', 'no', 'its', 'in', 'i', 'or', 'has'}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower()) if w not in STOPWORDS]


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 2]


def provider_status():
    """Report which optional model providers are configured (never exposes secrets)."""
    ollama = bool(os.getenv("OLLAMA_BASE_URL"))
    openai = bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_MODEL"))
    return {"ollama_compatible": ollama, "openai_compatible": openai}


def _llm(messages, temperature=0.2):
    """Call an explicitly configured OpenAI-compatible endpoint; return None when unavailable."""
    base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "")
    if not base or not model:
        ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        if not ollama:
            return None
        base = f"{ollama}/v1"
        model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        return None
    try:
        import httpx

        headers = {"Content-Type": "application/json"}
        key = os.getenv("OPENAI_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def _result(summary, result, warnings=None):
    return {"summary": summary, "result": result, "warnings": warnings or []}


def agent_device_intelligence(payload):
    hardware = _json(payload, "hardware", dict)
    try:
        cores = float(hardware.get("cpu_cores", 0))
        ram = float(hardware.get("ram_gb", 0))
        vram = float(hardware.get("vram_gb", 0) or 0)
        disk = float(hardware.get("disk_free_gb", 0) or 0)
    except (TypeError, ValueError):
        raise LogicError("hardware fields must be numeric")
    if cores <= 0 or ram <= 0:
        raise LogicError("hardware.cpu_cores and hardware.ram_gb must be positive")
    use_case = str(payload.get("use_case", "balanced")).lower()
    weights = {
        "coding": (0.60, 0.20),
        "chat": (0.45, 0.35),
        "speed": (0.25, 0.65),
        "balanced": (0.50, 0.30),
    }.get(use_case, (0.50, 0.30))
    catalog = [
        {"name": "Nano 1B", "params": 1, "ram": 4, "vram": 0, "disk": 2, "quality": 40, "speed": 96},
        {"name": "Mini 3B", "params": 3, "ram": 8, "vram": 4, "disk": 4, "quality": 58, "speed": 84},
        {"name": "Studio 7B", "params": 7, "ram": 16, "vram": 6, "disk": 8, "quality": 74, "speed": 66},
        {"name": "Pro 13B", "params": 13, "ram": 24, "vram": 10, "disk": 14, "quality": 84, "speed": 48},
        {"name": "Max 34B", "params": 34, "ram": 48, "vram": 24, "disk": 30, "quality": 93, "speed": 28},
    ]
    rows, findings = [], []
    for model in catalog:
        if ram < model["ram"] or disk < model["disk"]:
            fit, bonus = "unsupported", 0
        elif model["vram"] > 0 and vram < model["vram"]:
            fit, bonus = "cpu-only", 4
        else:
            fit, bonus = "accelerated", 10
        score = model["quality"] * weights[0] + model["speed"] * weights[1] + bonus
        rows.append([model["name"], model["params"], model["ram"], model["vram"], fit, round(score, 1)])
    rows.sort(key=lambda row: row[5], reverse=True)
    compatible = [row for row in rows if row[4] != "unsupported"]
    if not compatible:
        findings.append({"title": "No catalog model fits", "severity": "high", "detail": "Increase RAM or free disk space; all catalog models exceed the supplied limits."})
    if vram <= 0:
        findings.append({"title": "CPU-only profile", "severity": "info", "detail": "No GPU VRAM was supplied, so latency estimates assume CPU inference."})
    if disk < 10:
        findings.append({"title": "Low disk headroom", "severity": "medium", "detail": "Less than 10 GB free may prevent model downloads and caching."})
    best = compatible[0][0] if compatible else "none"
    return _result(
        f"Best fit for {use_case}: {best} ({len(compatible)} compatible catalog entries).",
        {
            "metrics": {"best_model": best, "compatible_models": len(compatible), "ram_gb": ram, "vram_gb": vram},
            "table": {"columns": ["Model", "Params (B)", "Min RAM (GB)", "Min VRAM (GB)", "Fit", "Score"], "rows": rows},
            "findings": findings,
        },
        ["Compatibility is rule-based and should be validated against the model's current requirements."],
    )


run = agent_device_intelligence
