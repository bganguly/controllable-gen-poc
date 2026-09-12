import os
import json
import anthropic
import openai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Controllable Gen POC", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_anthropic = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_openai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])

CONTROL_SPEC_SCHEMA = """{
  "subject": "<main subject of the image>",
  "style": "<photorealistic | cinematic | oil painting | watercolor | digital art | ...>",
  "composition": "<wide angle | portrait | aerial | close-up | rule of thirds | ...>",
  "lighting": "<golden hour | dramatic | soft diffused | rim light | neon | low-key | ...>",
  "atmosphere": "<clear | misty | stormy | dreamy | gritty | ethereal | ...>",
  "color_palette": "<warm | cool | monochromatic | vivid | desaturated | ...>",
  "mood": "<serene | dramatic | playful | melancholic | tense | mysterious | ...>",
  "details": ["<specific visual detail 1>", "<specific visual detail 2>"],
  "negative": "<elements to explicitly avoid>"
}"""

SYSTEM_EXTRACT = (
    "You are an expert visual composition analyst. "
    "Extract a structured control specification from the user's image description. "
    "Return JSON only, no markdown fences."
)
SYSTEM_REFINE = (
    "You are an expert visual composition analyst. "
    "Refine the given control spec based on user feedback. Return JSON only, no markdown fences."
)


class GenerateRequest(BaseModel):
    prompt: str
    provider: str = "anthropic"
    prev_control_spec: dict | None = None
    feedback: str | None = None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


# ── Anthropic (Claude) ─────────────────────────────────────────────────────────

def _extract_spec_anthropic(prompt: str, prev_spec: dict | None, feedback: str | None) -> dict:
    if prev_spec and feedback:
        system = SYSTEM_REFINE
        user_msg = (
            f"Previous spec:\n{json.dumps(prev_spec, indent=2)}\n\n"
            f"User feedback: {feedback}\n\n"
            f"Return an updated JSON spec:\n{CONTROL_SPEC_SCHEMA}"
        )
    else:
        system = SYSTEM_EXTRACT
        user_msg = f"User description: {prompt}\n\nReturn a JSON control spec:\n{CONTROL_SPEC_SCHEMA}"

    resp = _anthropic.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text if resp.content else None
    if not raw:
        raise ValueError("Empty response from Claude")
    return json.loads(_strip_json_fences(raw))


def _critique_anthropic(image_b64: str, spec: dict, original_prompt: str) -> str:
    resp = _anthropic.messages.create(
        model="claude-sonnet-5",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                },
                {
                    "type": "text",
                    "text": (
                        f"Original intent: {original_prompt}\n\n"
                        f"Control spec applied:\n{json.dumps(spec, indent=2)}\n\n"
                        "Critique this image in 2-3 sentences: what was captured well and what misses "
                        "the intent? End with one concrete suggestion for the next iteration."
                    ),
                },
            ],
        }],
    )
    return (resp.content[0].text if resp.content else None) or "Critique unavailable."


# ── OpenAI (GPT-4o) ───────────────────────────────────────────────────────────

def _extract_spec_openai(prompt: str, prev_spec: dict | None, feedback: str | None) -> dict:
    if prev_spec and feedback:
        messages = [
            {"role": "system", "content": SYSTEM_REFINE},
            {"role": "user", "content": (
                f"Previous spec:\n{json.dumps(prev_spec, indent=2)}\n\n"
                f"User feedback: {feedback}\n\n"
                f"Return an updated JSON spec:\n{CONTROL_SPEC_SCHEMA}"
            )},
        ]
    else:
        messages = [
            {"role": "system", "content": SYSTEM_EXTRACT},
            {"role": "user", "content": f"User description: {prompt}\n\nReturn a JSON control spec:\n{CONTROL_SPEC_SCHEMA}"},
        ]

    resp = _openai.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=messages,  # type: ignore[arg-type]
        max_tokens=1024,
    )
    raw = resp.choices[0].message.content or ""
    return json.loads(raw)


def _critique_openai(image_b64: str, spec: dict, original_prompt: str) -> str:
    resp = _openai.chat.completions.create(
        model="gpt-4o",
        messages=[{  # type: ignore[list-item]
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                {
                    "type": "text",
                    "text": (
                        f"Original intent: {original_prompt}\n\n"
                        f"Control spec applied:\n{json.dumps(spec, indent=2)}\n\n"
                        "Critique this image in 2-3 sentences: what was captured well and what misses "
                        "the intent? End with one concrete suggestion for the next iteration."
                    ),
                },
            ],
        }],
        max_tokens=512,
    )
    return resp.choices[0].message.content or "Critique unavailable."


# ── shared ────────────────────────────────────────────────────────────────────

def build_dalle_prompt(spec: dict) -> str:
    parts: list[str] = []
    if spec.get("subject"):
        parts.append(spec["subject"])
    if spec.get("style"):
        parts.append(f"{spec['style']} style")
    if spec.get("composition"):
        parts.append(f"{spec['composition']} composition")
    if spec.get("lighting"):
        parts.append(f"{spec['lighting']} lighting")
    if spec.get("atmosphere"):
        parts.append(spec["atmosphere"])
    if spec.get("color_palette"):
        parts.append(f"{spec['color_palette']} color palette")
    if spec.get("mood"):
        parts.append(f"{spec['mood']} mood")
    for detail in spec.get("details", []):
        parts.append(detail)
    prompt = ", ".join(parts)
    if spec.get("negative"):
        prompt += f". Avoid: {spec['negative']}"
    return prompt


def generate_image(dalle_prompt: str) -> str:
    resp = _openai.images.generate(
        model="gpt-image-1",
        prompt=dalle_prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return resp.data[0].b64_json  # type: ignore[union-attr]


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "Controllable Gen POC"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate(req: GenerateRequest):
    use_openai = req.provider == "openai"

    try:
        if use_openai:
            spec = _extract_spec_openai(req.prompt, req.prev_control_spec, req.feedback)
        else:
            spec = _extract_spec_anthropic(req.prompt, req.prev_control_spec, req.feedback)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Control spec extraction failed: {e}")

    dalle_prompt = build_dalle_prompt(spec)

    try:
        image_b64 = generate_image(dalle_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {e}")

    try:
        critique = _critique_openai(image_b64, spec, req.prompt) if use_openai \
            else _critique_anthropic(image_b64, spec, req.prompt)
    except Exception:
        critique = "Critique unavailable."

    return {
        "control_spec": spec,
        "dalle_prompt": dalle_prompt,
        "image_b64": image_b64,
        "critique": critique,
    }
