import { useState } from "react";
import { api } from "../api";
import { LANGS, useT } from "../i18n";

export default function SettingsPage({ profile, onSaved, onLogout }) {
  const t = useT(profile.language);
  const [f, setF] = useState({ ...profile });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "number" ? Number(e.target.value) : e.target.value });

  async function save(e) {
    e.preventDefault();
    setError(""); setMsg("");
    try {
      const { id, created_at, ...body } = f;
      onSaved(await api.updateProfile(profile.id, body));
      setMsg("Saved");
    } catch (err) { setError(err.message); }
  }

  return (
    <form className="card form" onSubmit={save}>
      <label>Name<input value={f.name} onChange={set("name")} autoComplete="name" /></label>
      <label>Registered mobile (for reminder calls and course updates)
        <input value={f.phone} readOnly inputMode="tel" />
      </label>
      <label>Caregiver phone (optional)
        <input value={f.caregiver_phone} onChange={set("caregiver_phone")} placeholder="+919812345678" inputMode="tel" />
      </label>
      <label>Language
        <select value={f.language} onChange={set("language")}>{Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      </label>
      <fieldset>
        <legend>Medicine times</legend>
        <div className="row4">
          {["morning", "afternoon", "evening", "night"].map((s) => (
            <label key={s}>{t(s)}<input type="time" value={f[`t_${s}`]} onChange={set(`t_${s}`)} /></label>
          ))}
        </div>
      </fieldset>
      <div className="row">
        <label>Call me after (min)<input type="number" min="1" max="60" value={f.escalation_min} onChange={set("escalation_min")} /></label>
        <label>Alert caregiver after call (min)<input type="number" min="1" max="120" value={f.caregiver_min} onChange={set("caregiver_min")} /></label>
      </div>
      <button className="primary">{t("saved")}</button>
      <button type="button" className="ghost" onClick={onLogout}>Sign out</button>
      {msg && <div className="banner info">{msg}</div>}
      {error && <div className="banner danger">{error}</div>}
      <p className="fine">Changing times affects reminders created after saving. Re-create reminders from a scan to apply new times.</p>
    </form>
  );
}
