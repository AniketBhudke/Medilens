import { useRef, useState } from "react";
import { api } from "../api";
import { LANGS, useT } from "../i18n";

const FOOD = { before_food: "Before food", after_food: "After food", with_food: "With food", empty_stomach: "Empty stomach", any: "" };
const SLOT_LABEL = { morning: "Morning", afternoon: "Afternoon", evening: "Evening", night: "Night" };

export default function ScanPage({ profile, onPlanCreated }) {
  const t = useT(profile.language);
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [language, setLanguage] = useState(profile.language);
  const [sex, setSex] = useState("unknown");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [courseDays, setCourseDays] = useState([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [removed, setRemoved] = useState(new Set());

  async function run(force = false) {
    if (!file) return;
    setBusy(true); setError(""); setResult(null); setAcknowledged(false); setRemoved(new Set());
    try {
      const report = await api.analyze(file, language, sex, force);
      setResult(report);
      setCourseDays(report.medicines.map((m) => m.duration_days ? String(m.duration_days) : ""));
    }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function createReminders() {
    const medicines = result.medicines
      .map((m, i) => ({ medicine: m, index: i }))
      .filter(({ index }) => !removed.has(index))
      .map(({ medicine: m, index }) => ({
        name: m.name, strength: m.strength || "", frequency_raw: m.frequency_raw || "",
        duration_days: m.schedulable ? Number(courseDays[index]) : m.duration_days,
        food_timing: m.food_timing || "any", how_to_take: m.how_to_take || "",
      }));
    try {
      const r = await api.createPlan(profile.id, { medicines, replace_existing: true });
      if (r.skipped?.length) alert("Not scheduled: " + r.skipped.map((s) => `${s.name} (${s.reason})`).join(", "));
      onPlanCreated();
    } catch (e) { setError(e.message); }
  }

  const needsAck = result?.status === "needs_verification";
  const durationMissing = result?.medicines.some((m, i) =>
    !removed.has(i) && m.schedulable && (!Number.isInteger(Number(courseDays[i])) || Number(courseDays[i]) < 1 || Number(courseDays[i]) > 60)
  );
  const canCreate = result && result.status !== "needs_reupload" && (!needsAck || acknowledged) && !durationMissing;

  return (
    <section>
      <div className="card">
        <button className="drop" onClick={() => fileRef.current.click()}>
          <strong>{file ? file.name : t("upload")}</strong>
          <span>{t("uploadHint")}</span>
        </button>
        <input ref={fileRef} type="file" accept="image/*,application/pdf" capture="environment" hidden
               onChange={(e) => { setFile(e.target.files[0] || null); setResult(null); }} />
        <div className="row">
          <label>{t("explain")}
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label>Sex (for lab ranges)
            <select value={sex} onChange={(e) => setSex(e.target.value)}>
              <option value="unknown">Not specified</option><option value="female">Female</option><option value="male">Male</option>
            </select>
          </label>
        </div>
        <button className="primary" disabled={!file || busy} onClick={() => run(false)}>{busy ? t("reading") : t("analyze")}</button>
        {error && <div className="banner danger" role="alert">{error}</div>}
      </div>

      {result?.status === "needs_reupload" && (
        <div className="banner warn" role="alert">
          <strong>Photo not clear enough</strong>
          <p>{result.message}</p>
          <ul>{result.quality.issues.map((i) => <li key={i}>{i}</li>)}</ul>
          <button className="ghost" onClick={() => run(true)}>Try anyway</button>
        </div>
      )}

      {result && result.status !== "needs_reupload" && (
        <>
          {result.demo && <div className="banner info">Demo data — add an ANTHROPIC_API_KEY on the server to read real documents.</div>}
          {needsAck && (
            <div className="banner warn" role="alert">
              <strong>Low confidence reading</strong>
              <p>{t("verify")}</p>
              {result.legibility_issues.length > 0 && <ul>{result.legibility_issues.map((i, k) => <li key={k}>{i}</li>)}</ul>}
              <label className="check"><input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} /> I will confirm with my pharmacist or doctor</label>
            </div>
          )}

          {result.summary && <div className="card"><p className="lead">{result.summary}</p></div>}

          {result.warnings.map((w, i) => (
            <div key={i} className={`banner ${w.severity === "high" ? "danger" : "warn"}`} role="alert">
              <strong>{w.type === "duplicate" ? "Same medicine twice" : "Medicines that clash"}</strong>
              <p>{w.message}</p>
            </div>
          ))}

          {result.medicines.length > 0 && <h2>Medicines</h2>}
          {result.medicines.map((m, i) => (
            <article key={i} className={`card med ${removed.has(i) ? "off" : ""} ${m.low_confidence ? "uncertain" : ""}`}>
              <div className="med-head">
                <h3>{m.name} <small>{m.strength}</small></h3>
                <button className="link" onClick={() => setRemoved((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; })}>
                  {removed.has(i) ? "Add back" : "Remove"}
                </button>
              </div>
              {m.purpose && <p>{m.purpose}</p>}
              <p className="how">{m.how_to_take}</p>
              <div className="tags">
                {Object.keys(m.parsed_slots || {}).map((s) => <span key={s} className="tag">{SLOT_LABEL[s]} × {m.parsed_slots[s]}</span>)}
                {m.as_needed && <span className="tag">Only when needed</span>}
                {FOOD[m.food_timing] && <span className="tag">{FOOD[m.food_timing]}</span>}
                {m.low_confidence && <span className="tag bad">Unclear — verify</span>}
                {!m.schedulable && !m.as_needed && <span className="tag bad">Timing not readable</span>}
              </div>
              {m.schedulable && !removed.has(i) && (
                <label className="course-days">Course length (days — check the prescription)
                  <input type="number" min="1" max="60" value={courseDays[i] || ""}
                         onChange={(e) => setCourseDays((days) => days.map((d, k) => k === i ? e.target.value : d))} />
                </label>
              )}
              {m.abbreviations?.length > 0 && (
                <dl>{m.abbreviations.map((a, k) => <div key={k}><dt>{a.abbr}</dt><dd>{a.meaning}</dd></div>)}</dl>
              )}
            </article>
          ))}

          {result.lab_results.length > 0 && (
            <>
              <h2>Lab results {result.abnormal_count > 0 && <small>{result.abnormal_count} outside range</small>}</h2>
              <div className="card labs">
                {result.lab_results.map((r, i) => (
                  <div key={i} className={`lab ${r.flag}`}>
                    <div>
                      <strong>{r.test}</strong>
                      <span className="ref">{r.reference ? `Normal: ${r.reference}` : r.reference_range_text || ""}</span>
                    </div>
                    <div className="val">
                      <b>{r.value}</b> <small>{r.unit}</small>
                      <span className={`flag ${r.flag}`}>{r.flag === "high" ? "▲ High" : r.flag === "low" ? "▼ Low" : r.flag === "normal" ? "✓ " + t("normal") : "?"}</span>
                    </div>
                    {(r.explanation || r.default_note) && <p>{r.explanation}{r.flag !== "normal" && r.default_note ? ` ${r.default_note}` : ""}</p>}
                  </div>
                ))}
              </div>
            </>
          )}

          <p className="fine">{result.disclaimer}</p>
          {result.medicines.length > 0 && (
            <button className="primary sticky" disabled={!canCreate} onClick={createReminders}>{t("makeReminders")}</button>
          )}
        </>
      )}
    </section>
  );
}
