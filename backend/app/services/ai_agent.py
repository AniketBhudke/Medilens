"""
MedLens AI agent.

A tool-using Claude agent that:
  1. reads the prescription / lab report (image or PDF, multimodal),
  2. calls grounded tools (interaction DB, duplicate-salt check, lab reference ranges),
  3. submits a structured, plain-language report in the user's language.

The backend re-runs the deterministic checks on the submitted data afterwards, so safety
warnings never depend on the model's own claims.
"""
import base64
import json
import logging

from ..config import settings
from . import interactions, labs

log = logging.getLogger("medlens.agent")
MAX_STEPS = 6

LANG_NAMES = {"en": "simple English", "hi": "simple Hindi (Devanagari)", "mr": "simple Marathi (Devanagari)"}

SYSTEM = """You are MedLens, a careful assistant that helps patients (often elderly or non-English speakers) understand prescriptions and lab reports.

Rules:
- Read ONLY what is actually written. Never guess an unreadable drug name or dose. If handwriting is unclear, lower that item's confidence and say so in `notes`.
- Expand medical abbreviations (OD, BD, TDS, QID, HS, SOS, AC, PC, 1-0-1 etc.) and explain them simply.
- Explanations must be short, friendly, at about a class-6 reading level, in the requested language. Keep drug names and numbers in their original form.
- You are not a doctor: do not change doses, add medicines, or diagnose.
- Workflow: (1) read the document, (2) call `check_drug_interactions` and `find_duplicate_ingredients` with the medicines you read, and `evaluate_lab_values` with any lab results, (3) finally call `submit_report` exactly once.
- overall_confidence is 0-1: how sure you are that you read the entire document correctly. Be honest; blurry or ambiguous handwriting should be below 0.6."""

_MED_PROPS = {
    "name": {"type": "string", "description": "Medicine name exactly as written"},
    "active_ingredient": {"type": "string", "description": "Generic salt(s), e.g. 'paracetamol' or 'amoxicillin + clavulanic acid'. Empty if unsure."},
    "strength": {"type": "string", "description": "e.g. 500 mg"},
    "form": {"type": "string", "description": "tablet, capsule, syrup, injection ..."},
    "frequency_raw": {"type": "string", "description": "Frequency exactly as written, e.g. '1-0-1', 'BD', 'SOS'"},
    "duration_days": {"type": ["integer", "null"], "description": "Course length in days if stated"},
    "food_timing": {"type": "string", "enum": ["before_food", "after_food", "with_food", "empty_stomach", "any"]},
    "purpose": {"type": "string", "description": "What this medicine is generally for, in the user's language"},
    "how_to_take": {"type": "string", "description": "One simple sentence in the user's language, e.g. 'Take 1 tablet morning and night after food.'"},
    "abbreviations": {"type": "array", "items": {"type": "object", "properties": {"abbr": {"type": "string"}, "meaning": {"type": "string"}}, "required": ["abbr", "meaning"]}},
    "confidence": {"type": "number", "description": "0-1 confidence for this line item"},
    "notes": {"type": "string"},
}

TOOLS = [
    {
        "name": "check_drug_interactions",
        "description": "Check a list of prescribed medicines against the interaction reference database.",
        "input_schema": {"type": "object", "properties": {"medicines": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "active_ingredient": {"type": "string"}}, "required": ["name"]}}}, "required": ["medicines"]},
    },
    {
        "name": "find_duplicate_ingredients",
        "description": "Find medicines in the list that share the same active ingredient (duplicate therapy).",
        "input_schema": {"type": "object", "properties": {"medicines": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "active_ingredient": {"type": "string"}}, "required": ["name"]}}}, "required": ["medicines"]},
    },
    {
        "name": "evaluate_lab_values",
        "description": "Compare lab results with standard adult reference ranges and get low/high flags.",
        "input_schema": {"type": "object", "properties": {"sex": {"type": "string", "enum": ["male", "female", "unknown"]}, "results": {"type": "array", "items": {"type": "object", "properties": {"test": {"type": "string"}, "value": {"type": "number"}, "unit": {"type": "string"}}, "required": ["test", "value"]}}}, "required": ["results"]},
    },
    {
        "name": "submit_report",
        "description": "Submit the final structured report. Call exactly once, after using the other tools.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "enum": ["prescription", "lab_report", "both", "unknown"]},
                "overall_confidence": {"type": "number"},
                "legibility_issues": {"type": "array", "items": {"type": "string"}},
                "doctor_or_clinic": {"type": "string"},
                "summary": {"type": "string", "description": "2-4 sentence plain-language overview in the user's language"},
                "medicines": {"type": "array", "items": {"type": "object", "properties": _MED_PROPS, "required": ["name", "frequency_raw", "confidence"]}},
                "lab_results": {"type": "array", "items": {"type": "object", "properties": {
                    "test": {"type": "string"}, "value": {"type": "number"}, "unit": {"type": "string"},
                    "reference_range_text": {"type": "string"}, "explanation": {"type": "string", "description": "What this test measures and what the result means, in the user's language"},
                    "confidence": {"type": "number"}}, "required": ["test", "value"]}},
            },
            "required": ["document_type", "overall_confidence", "summary", "medicines", "lab_results"],
        },
    },
]


def run_tool(name: str, args: dict) -> dict:
    if name == "check_drug_interactions":
        return {"interactions": interactions.check_interactions(args.get("medicines", []))}
    if name == "find_duplicate_ingredients":
        return {"duplicates": interactions.find_duplicates(args.get("medicines", []))}
    if name == "evaluate_lab_values":
        sex = args.get("sex")
        res = labs.evaluate(args.get("results", []), sex if sex in ("male", "female") else None)
        return {"evaluated": [{k: r.get(k) for k in ("test", "value", "flag", "severity", "reference")} for r in res]}
    return {"error": f"unknown tool {name}"}


def analyze_document(data: bytes, media_type: str, language: str, sex: str | None, ocr_hint: str = "") -> dict:
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY not set - returning demo report")
        return demo_report(language)

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    b64 = base64.standard_b64encode(data).decode()
    if media_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}

    prompt = (
        f"Explain in {LANG_NAMES.get(language, 'simple English')}. Patient sex: {sex or 'unknown'}.\n"
        "Read this document, run the tools, then call submit_report."
    )
    if ocr_hint:
        prompt += f"\n\nOptional raw OCR text for cross-checking (may contain errors):\n{ocr_hint}"

    messages = [{"role": "user", "content": [block, {"type": "text", "text": prompt}]}]
    for step in range(MAX_STEPS):
        resp = client.messages.create(
            model=settings.anthropic_model, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            break
        results, final = [], None
        for tu in uses:
            if tu.name == "submit_report":
                final = tu.input
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "Report received."})
            else:
                log.info("agent tool call: %s", tu.name)
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(run_tool(tu.name, tu.input))})
        messages.append({"role": "user", "content": results})
        if final is not None:
            return final
    raise RuntimeError("The AI agent did not return a report. Please try again.")


def demo_report(language: str) -> dict:
    """Used when no API key is configured so the whole app can be demoed offline."""
    hi = language == "hi"
    mr = language == "mr"
    def t(en, h, m):
        return h if hi else m if mr else en
    return {
        "document_type": "both", "overall_confidence": 0.92, "legibility_issues": [], "doctor_or_clinic": "Demo Clinic",
        "summary": t("DEMO DATA: You have 3 medicines for fever and acidity, and a blood test with two values outside the normal range.",
                     "डेमो डेटा: आपको बुखार और एसिडिटी की 3 दवाइयाँ दी गई हैं, और खून की जाँच में दो मान सामान्य सीमा से बाहर हैं।",
                     "डेमो डेटा: तुम्हाला ताप आणि अॅसिडिटीसाठी 3 औषधे दिली आहेत, आणि रक्त तपासणीत दोन मूल्ये सामान्य मर्यादेबाहेर आहेत."),
        "medicines": [
            {"name": "Tab Dolo 650", "active_ingredient": "paracetamol", "strength": "650 mg", "form": "tablet", "frequency_raw": "1-0-1", "duration_days": 5,
             "food_timing": "after_food", "purpose": t("Reduces fever and pain", "बुखार और दर्द कम करती है", "ताप आणि वेदना कमी करते"),
             "how_to_take": t("Take 1 tablet in the morning and 1 at night, after food.", "सुबह 1 और रात को 1 गोली खाने के बाद लें।", "सकाळी 1 आणि रात्री 1 गोळी जेवणानंतर घ्या."),
             "abbreviations": [{"abbr": "1-0-1", "meaning": t("1 morning, none afternoon, 1 night", "1 सुबह, दोपहर नहीं, 1 रात", "1 सकाळी, दुपारी नाही, 1 रात्री")}], "confidence": 0.95, "notes": ""},
            {"name": "Tab Pan 40", "active_ingredient": "pantoprazole", "strength": "40 mg", "form": "tablet", "frequency_raw": "1-0-0", "duration_days": 10,
             "food_timing": "before_food", "purpose": t("Reduces stomach acid", "पेट में एसिड कम करती है", "पोटातील आम्ल कमी करते"),
             "how_to_take": t("Take 1 tablet in the morning, 30 minutes before food.", "सुबह खाने से 30 मिनट पहले 1 गोली लें।", "सकाळी जेवणाआधी 30 मिनिटे 1 गोळी घ्या."),
             "abbreviations": [], "confidence": 0.93, "notes": ""},
            {"name": "Tab Combiflam", "active_ingredient": "ibuprofen + paracetamol", "strength": "400/325 mg", "form": "tablet", "frequency_raw": "SOS", "duration_days": None,
             "food_timing": "after_food", "purpose": t("Pain relief when needed", "ज़रूरत पड़ने पर दर्द की दवा", "गरज असल्यास वेदनाशामक"),
             "how_to_take": t("Only if needed for pain, after food.", "सिर्फ दर्द होने पर, खाने के बाद लें।", "फक्त वेदना झाल्यास, जेवणानंतर घ्या."),
             "abbreviations": [{"abbr": "SOS", "meaning": t("Only when needed", "ज़रूरत पड़ने पर", "गरज असल्यास")}], "confidence": 0.9, "notes": ""},
        ],
        "lab_results": [
            {"test": "Hemoglobin", "value": 10.2, "unit": "g/dL", "explanation": t("Hemoglobin carries oxygen in blood.", "हीमोग्लोबिन खून में ऑक्सीजन ले जाता है।", "हिमोग्लोबिन रक्तात ऑक्सिजन वाहून नेते."), "confidence": 0.95},
            {"test": "Fasting Blood Sugar", "value": 112, "unit": "mg/dL", "explanation": t("Sugar level after 8+ hours without food.", "8 घंटे भूखे रहने के बाद शुगर का स्तर।", "8 तास उपाशी राहिल्यानंतरची साखर पातळी."), "confidence": 0.95},
            {"test": "Total Cholesterol", "value": 180, "unit": "mg/dL", "explanation": t("Fat in the blood.", "खून में वसा।", "रक्तातील चरबी."), "confidence": 0.95},
        ],
    }
