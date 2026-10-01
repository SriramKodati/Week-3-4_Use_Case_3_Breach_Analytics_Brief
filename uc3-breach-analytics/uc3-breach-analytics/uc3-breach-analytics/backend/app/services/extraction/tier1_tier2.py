"""
Tier 1 (cheap/routine) and Tier 2 (escalation) LLM extraction. Handles
categories Tier 0's regex/checksum approach genuinely can't: names,
driver's license/passport numbers (no universal format), medical notes,
login credentials, and name variants. Tier 0 output is NOT re-extracted
here — this stage only fills the gap Tier 0 leaves.

Same provider-swap pattern as Weeks 1-2: local Ollama by default (zero
API keys), DeepSeek for Tier 1, Claude for Tier 2/escalation/agents.
"""
import json
from pydantic import BaseModel, ValidationError

from app.core.config import settings

EXTRACTION_PROMPT = """Extract any of the following personal data elements mentioned in this text, \
if present. Do not invent values that are not in the text.

Return JSON matching this structure exactly:
{{
  "person_name": string or null,
  "address": string or null,
  "driver_license": string or null,
  "passport": string or null,
  "medical_note": string or null,
  "login_credential": string or null,
  "self_assessed_confidence": number from 0 to 1 for how certain you are these values are correct
}}

Return ONLY the JSON object, no other text. Use compact JSON on a single line.

TEXT:
{text}"""


class Tier1Extraction(BaseModel):
    person_name: str | None = None
    address: str | None = None
    driver_license: str | None = None
    passport: str | None = None
    medical_note: str | None = None
    login_credential: str | None = None
    self_assessed_confidence: float = 0.5


def _call_local(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key="ollama", base_url=f"{settings.ollama_base_url}/v1")
    resp = client.chat.completions.create(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    return resp.choices[0].message.content or ""


def _call_deepseek(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.deepseek_api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content or ""


def _call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(model="claude-sonnet-4-6", max_tokens=800,
                                      messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in message.content if b.type == "text")


TIER_PROVIDERS = {"local": _call_local, "deepseek": _call_deepseek, "anthropic": _call_anthropic}


def _repair_brackets(text: str) -> str:
    """Same bracket-balance repair developed in Week 2 after live testing
    showed small models truncate JSON on longer documents."""
    stack, in_string, escape = [], False, False
    for ch in text:
        if in_string:
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': in_string = False
            continue
        if ch == '"': in_string = True
        elif ch in "{[": stack.append(ch)
        elif ch in "}]" and stack: stack.pop()
    closers = {"{": "}", "[": "]"}
    repaired = text + ('"' if in_string else "")
    for opener in reversed(stack):
        repaired += closers[opener]
    return repaired


def extract_tier(text: str, tier: int, max_retries: int = 2) -> tuple[Tier1Extraction | None, str | None]:
    """tier: 1 or 2 — selects which provider setting to use. Returns
    (extraction, error)."""
    provider_name = settings.tier1_provider if tier == 1 else settings.tier2_provider
    fn = TIER_PROVIDERS.get(provider_name)
    if fn is None:
        return None, f"Unknown provider for tier {tier}: {provider_name}"

    prompt = EXTRACTION_PROMPT.format(text=text[:4000])  # cap input for cost control
    last_error = None

    for attempt in range(max_retries + 1):
        raw = fn(prompt if attempt == 0 else prompt + "\n\nReturn corrected, compact single-line JSON only.")
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                data = json.loads(_repair_brackets(cleaned))
            except json.JSONDecodeError as e:
                last_error = f"invalid JSON: {e}"
                continue

        try:
            return Tier1Extraction(**data), None
        except ValidationError as e:
            last_error = f"schema validation failed: {e}"
            continue

    return None, last_error
