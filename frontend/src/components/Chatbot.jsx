import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  async function send(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

    const conversation = [...messages, { role: "user", content: text }];
    const context = conversation.slice(-12);
    if (context[0]?.role === "assistant") context.shift();
    setMessages(conversation);
    setDraft("");
    setError("");
    setBusy(true);
    try {
      const result = await api.chat(context);
      setDemo(Boolean(result.demo));
      setMessages([...conversation, { role: "assistant", content: result.answer }]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat-widget">
      {open && (
        <section className="chat-panel" role="dialog" aria-modal="false" aria-labelledby="chat-title">
          <header className="chat-header">
            <div>
              <strong id="chat-title">Ask MedLens</strong>
              <span>Medicine information</span>
            </div>
            <div className="chat-header-actions">
              <button type="button" className="link" onClick={() => { setMessages([]); setError(""); setDemo(false); }}>Clear</button>
              <button type="button" className="chat-close" onClick={() => setOpen(false)} aria-label="Close chat">×</button>
            </div>
          </header>
          <div className="chat-messages" aria-live="polite">
            {demo && <div className="chat-demo-note" role="status">Demo answer: sample medicine information only. Configure an Anthropic key for open-ended questions.</div>}
            {messages.length === 0 && (
              <p className="chat-intro">Ask about a tablet’s general use, your listed medicines, or prescription wording. This is general information, not medical advice.</p>
            )}
            {messages.map((message, index) => (
              <div key={`${index}-${message.role}`} className={`chat-message ${message.role}`}>
                <span>{message.role === "user" ? "You" : "MedLens"}</span>
                <p>{message.content}</p>
              </div>
            ))}
            {busy && <p className="chat-working">MedLens is preparing an answer…</p>}
            {error && <div className="banner danger" role="alert">{error}</div>}
            <div ref={endRef} />
          </div>
          <form className="chat-form" onSubmit={send}>
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)}
                      placeholder="Ask a medicine question…" maxLength="2000" rows="2"
                      aria-label="Your medicine question" disabled={busy} />
            <button className="primary small" disabled={busy || !draft.trim()}>Send</button>
          </form>
          <p className="chat-disclaimer">For personal dose or safety decisions, ask your doctor or pharmacist. Emergency symptoms need urgent care.</p>
        </section>
      )}
      <button type="button" className={`chat-fab${open ? " is-open" : ""}`} onClick={() => setOpen((value) => !value)}
              aria-expanded={open} aria-label={open ? "Close medicine chat" : "Open medicine chat"}>
        <svg className="chat-fab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {open
            ? <path d="m6 6 12 12M18 6 6 18" />
            : <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 8 8 0 0 1-3.2-.7L4 20l1.5-4A7.5 7.5 0 1 1 20 11.5Z" />}
        </svg>
        <span className="chat-fab-label">{open ? "Close chat" : "Ask MedLens"}</span>
      </button>
    </div>
  );
}
