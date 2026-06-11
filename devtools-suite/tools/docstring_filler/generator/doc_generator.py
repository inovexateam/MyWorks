"""
AI generator: takes a MissingDoc and returns a formatted docstring.
Uses GitHub Copilot API (OpenAI-compatible endpoint) or falls back
to a rule-based generator when no API key is available.

The key insight: we send the full signature + body snippet as context,
so the AI generates semantically meaningful docs, not just boilerplate.
"""

import os
import re
import json
import urllib.request
from core.models import MissingDoc, GeneratedDoc, DocStyle


# ── Style formatters ──────────────────────────────────────────────────────────

def format_xml_doc(summary: str, params: list[tuple], returns: str, exceptions: list[str]) -> str:
    lines = ["/// <summary>"]
    for s in summary.split('. '):
        if s.strip():
            lines.append(f"/// {s.strip()}.")
    lines.append("/// </summary>")
    for name, desc in params:
        lines.append(f'/// <param name="{name}">{desc}</param>')
    if returns:
        lines.append(f"/// <returns>{returns}</returns>")
    for exc in exceptions:
        lines.append(f'/// <exception cref="{exc}">Thrown when operation fails.</exception>')
    return '\n'.join(lines)


def format_javadoc(summary: str, params: list[tuple], returns: str, exceptions: list[str]) -> str:
    lines = ["/**", f" * {summary}"]
    if params or returns or exceptions:
        lines.append(" *")
    for name, desc in params:
        lines.append(f" * @param {name} {desc}")
    if returns:
        lines.append(f" * @return {returns}")
    for exc in exceptions:
        lines.append(f" * @throws {exc} if operation fails")
    lines.append(" */")
    return '\n'.join(lines)


def format_jsdoc(summary: str, params: list[tuple], returns: str, exceptions: list[str]) -> str:
    lines = ["/**", f" * {summary}"]
    if params or returns:
        lines.append(" *")
    for name, desc in params:
        lines.append(f" * @param {name} - {desc}")
    if returns:
        lines.append(f" * @returns {returns}")
    lines.append(" */")
    return '\n'.join(lines)


FORMATTERS = {
    DocStyle.XML_DOC: format_xml_doc,
    DocStyle.JAVADOC: format_javadoc,
    DocStyle.JSDOC:   format_jsdoc,
}

LANG_STYLES = {
    'csharp': DocStyle.XML_DOC,
    'java':   DocStyle.JAVADOC,
    'angular': DocStyle.JSDOC,
}


# ── Parameter extractor ───────────────────────────────────────────────────────

PARAM_RE = re.compile(r'(\w+)\s*(?::\s*[\w<>|?[\]]+)?\s*(?:,|\))')

def extract_params(signature: str) -> list[str]:
    paren = re.search(r'\(([^)]*)\)', signature)
    if not paren:
        return []
    raw = paren.group(1)
    # Handle C#/Java/TS params: "Type name" or "name: Type"
    params = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        # TypeScript: name: Type
        m = re.match(r'(\w+)\s*:', part)
        if m:
            params.append(m.group(1))
            continue
        # Java/C#: Type name
        tokens = part.split()
        if len(tokens) >= 2:
            params.append(tokens[-1].strip('[]'))
        elif tokens:
            params.append(tokens[0])
    return [p for p in params if p and p not in ('void', 'this', 'self')]


def extract_return_type(signature: str, language: str) -> str:
    if language == 'angular':
        m = re.search(r'\)\s*:\s*([\w<>|?[\]]+)', signature)
        return m.group(1) if m and m.group(1) not in ('void', 'never', 'Promise<void>') else ""
    # C# / Java: return type before method name
    m = re.match(r'\s*(?:public|private|protected|internal|static|final|abstract|virtual|override|async|\s)+\s+([\w<>\[\]?,]+)\s+\w+\s*\(', signature)
    if m:
        rt = m.group(1)
        return rt if rt not in ('void', 'Void') else ""
    return ""


# ── AI generation ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior developer writing precise, concise documentation.
Generate a docstring for the given code symbol.
Respond ONLY with a JSON object with these fields:
  summary: one sentence explaining what this does (not "This method...")
  params: object mapping param name to description (omit if none)
  returns: what is returned (omit if void/nothing)
  throws: list of exception types that may be thrown (omit if none)

Be specific. Infer behavior from the method name and body. No boilerplate."""


def build_prompt(symbol: MissingDoc) -> str:
    ctx = f"Class: {symbol.class_context}\n" if symbol.class_context else ""
    return f"""{ctx}Signature: {symbol.signature}

Body:
{symbol.body_snippet}

Generate documentation JSON."""


def call_ai_api(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> dict | None:
    """
    Calls OpenAI-compatible API (works with GitHub Copilot, Azure OpenAI, etc.).
    Returns parsed JSON dict or None on failure.
    """
    endpoint = os.environ.get("OPENAI_API_BASE", "https://api.openai.com")
    url = f"{endpoint}/v1/chat/completions"

    payload = json.dumps({
        "model": model,
        "max_tokens": 300,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            text = re.sub(r'^```json\s*|```$', '', text.strip(), flags=re.MULTILINE).strip()
            return json.loads(text), data.get("usage", {}).get("total_tokens", 0)
    except Exception:
        return None, 0


# ── Rule-based fallback ───────────────────────────────────────────────────────

VERB_MAP = {
    'get': 'Gets', 'set': 'Sets', 'create': 'Creates', 'build': 'Builds',
    'add': 'Adds', 'remove': 'Removes', 'update': 'Updates', 'delete': 'Deletes',
    'fetch': 'Fetches', 'load': 'Loads', 'save': 'Saves', 'process': 'Processes',
    'validate': 'Validates', 'check': 'Checks', 'init': 'Initializes',
    'parse': 'Parses', 'format': 'Formats', 'convert': 'Converts',
    'send': 'Sends', 'receive': 'Receives', 'handle': 'Handles',
    'calculate': 'Calculates', 'compute': 'Computes', 'find': 'Finds',
    'search': 'Searches', 'filter': 'Filters', 'sort': 'Sorts',
    'register': 'Registers', 'subscribe': 'Subscribes', 'publish': 'Publishes',
}

def camel_to_words(name: str) -> str:
    words = re.sub(r'([A-Z])', r' \1', name).split()
    return ' '.join(w.lower() for w in words if w)

def rule_based_summary(symbol: MissingDoc) -> str:
    words = camel_to_words(symbol.name).split()
    if not words:
        return f"Performs {symbol.name} operation."
    verb = words[0]
    mapped = VERB_MAP.get(verb, verb.capitalize())
    rest = ' '.join(words[1:]) if len(words) > 1 else symbol.class_context or 'the operation'
    return f"{mapped} {rest}."


def generate_fallback(symbol: MissingDoc) -> dict:
    return {
        "summary": rule_based_summary(symbol),
        "params": {p: f"The {camel_to_words(p)}" for p in extract_params(symbol.signature)},
        "returns": "",
        "throws": [],
    }


# ── Main generator ────────────────────────────────────────────────────────────

def generate_docstring(
    symbol: MissingDoc,
    api_key: str = "",
    model: str = "gpt-4o-mini",
) -> GeneratedDoc:
    style = LANG_STYLES.get(symbol.language, DocStyle.JSDOC)
    formatter = FORMATTERS[style]
    tokens = 0
    confidence = 0.0

    if api_key:
        prompt = build_prompt(symbol)
        result, tokens = call_ai_api(prompt, api_key, model)
        confidence = 0.85 if result else 0.0
    else:
        result = None

    if not result:
        result = generate_fallback(symbol)
        confidence = 0.4

    summary    = result.get("summary", rule_based_summary(symbol))
    raw_params = result.get("params", {})
    returns    = result.get("returns", "")
    throws     = result.get("throws", [])

    params = [(k, v) for k, v in raw_params.items()] if isinstance(raw_params, dict) else []

    docstring = formatter(summary, params, returns, throws)

    return GeneratedDoc(
        symbol=symbol,
        docstring=docstring,
        confidence=confidence,
        style=style,
        tokens_used=tokens,
    )


def generate_batch(
    symbols: list[MissingDoc],
    api_key: str = "",
    model: str = "gpt-4o-mini",
    max_symbols: int = 200,
    verbose: bool = False,
) -> list[GeneratedDoc]:
    """Generate docstrings for a batch of symbols."""
    results = []
    targets = symbols[:max_symbols]

    for i, sym in enumerate(targets):
        doc = generate_docstring(sym, api_key, model)
        results.append(doc)
        if verbose and (i + 1) % 10 == 0:
            print(f"\r  Generated {i+1}/{len(targets)}...", end='', flush=True)

    if verbose:
        print(f"\r  Generated {len(results)} docstrings.        ")

    return results
