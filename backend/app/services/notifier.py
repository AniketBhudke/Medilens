"""Voice-call / missed-call / SMS delivery via Twilio, with a MOCK mode when keys are absent."""
import logging
from xml.sax.saxutils import escape

from ..config import settings

log = logging.getLogger("medlens.notifier")

VOICE = {"en": ("en-IN", "Polly.Aditi"), "hi": ("hi-IN", "Polly.Aditi"), "mr": ("hi-IN", "Polly.Aditi")}  # Twilio has no Marathi TTS; Hindi voice reads Devanagari

MSG = {
    "en": "Hello {name}. This is MedLens. It is time for your medicine: {meds}. Please take it now, and open the app to confirm.",
    "hi": "नमस्ते {name}। यह मेडलेंस है। आपकी दवा का समय हो गया है: {meds}। कृपया अभी दवा लें और ऐप में पुष्टि करें।",
    "mr": "नमस्कार {name}. हा मेडलेन्स आहे. तुमच्या औषधाची वेळ झाली आहे: {meds}. कृपया आत्ता औषध घ्या आणि अॅपमध्ये पुष्टी करा.",
}
CAREGIVER_SMS = {
    "en": "MedLens alert: {name} has not confirmed taking: {meds} (due {time}). Please check on them.",
    "hi": "मेडलेंस अलर्ट: {name} ने {meds} लेने की पुष्टि नहीं की ({time})। कृपया उनसे संपर्क करें।",
    "mr": "मेडलेन्स अलर्ट: {name} यांनी {meds} घेतल्याची पुष्टी केली नाही ({time}). कृपया त्यांच्याशी संपर्क करा.",
}
COURSE_COMPLETE_SMS = {
    "en": "MedLens: Your prescribed course of {meds} is complete. Please follow your doctor's instructions.",
    "hi": "मेडलेंस: {meds} का निर्धारित कोर्स पूरा हो गया है। कृपया अपने डॉक्टर के निर्देशों का पालन करें।",
    "mr": "मेडलेन्स: {meds} चा निर्धारित कोर्स पूर्ण झाला आहे. कृपया डॉक्टरांच्या सूचनांचे पालन करा.",
}


def _client():
    from twilio.rest import Client
    return Client(settings.twilio_sid, settings.twilio_token)


def place_reminder_call(phone: str, name: str, meds: str, language: str) -> tuple[str, str]:
    """Return (sid, status). In voice mode a TTS call is placed; in missed mode the phone rings and we hang up."""
    if not phone:
        return "", "no_phone"
    if not settings.twilio_ready:
        log.warning("[MOCK CALL %s] to=%s name=%s meds=%s", settings.call_mode, phone, name, meds)
        return "MOCK-" + phone[-4:], "mock"
    lang, voice = VOICE.get(language, VOICE["en"])
    if settings.call_mode == "missed":
        twiml = "<Response><Pause length=\"1\"/><Hangup/></Response>"
    else:
        text = escape(MSG.get(language, MSG["en"]).format(name=name or "", meds=meds))
        twiml = f'<Response><Say language="{lang}" voice="{voice}">{text}</Say><Pause length="1"/><Say language="{lang}" voice="{voice}">{text}</Say></Response>'
    call = _client().calls.create(
        to=phone, from_=settings.twilio_from, twiml=twiml,
        status_callback=f"{settings.public_base_url}/api/webhooks/twilio/status", status_callback_event=["completed"],
        timeout=25,
    )
    return call.sid, "queued"


def send_caregiver_sms(phone: str, name: str, meds: str, time_local: str, language: str) -> str:
    if not phone:
        return "no_phone"
    body = CAREGIVER_SMS.get(language, CAREGIVER_SMS["en"]).format(name=name or "Patient", meds=meds, time=time_local)
    if not settings.twilio_ready:
        log.warning("[MOCK CAREGIVER SMS] to=%s body=%s", phone, body)
        return "mock"
    # For WhatsApp use from_="whatsapp:+14155238886", to=f"whatsapp:{phone}" (Twilio sandbox / approved sender)
    msg = _client().messages.create(to=phone, from_=settings.twilio_from, body=body)
    return msg.sid


def send_auth_code(phone: str, code: str, purpose: str) -> str:
    action = "verify your MedLens account" if purpose == "signup" else "reset your MedLens password"
    body = f"Your MedLens code to {action} is {code}. It expires in 10 minutes."
    if not settings.twilio_ready:
        log.warning("[MOCK AUTH SMS] to=%s purpose=%s code=%s", phone, purpose, code)
        return "mock"
    return _client().messages.create(to=phone, from_=settings.twilio_from, body=body).sid


def send_course_completion_sms(phone: str, meds: str, language: str) -> str:
    if not phone:
        return "no_phone"
    body = COURSE_COMPLETE_SMS.get(language, COURSE_COMPLETE_SMS["en"]).format(meds=meds)
    if not settings.twilio_ready:
        log.warning("[MOCK COURSE COMPLETE SMS] to=%s body=%s", phone, body)
        return "mock"
    return _client().messages.create(to=phone, from_=settings.twilio_from, body=body).sid
