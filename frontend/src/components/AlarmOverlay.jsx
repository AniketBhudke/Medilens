import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { startAlarm, stopAlarm } from "../sound";

export default function AlarmOverlay({ profile }) {
  const t = useT(profile.language);
  const [alarms, setAlarms] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    const poll = () => api.alarms(profile.id).then((r) => live && setAlarms(r.alarms)).catch(() => {});
    poll();
    const id = setInterval(poll, 5000);
    return () => { live = false; clearInterval(id); };
  }, [profile.id]);

  useEffect(() => {
    if (alarms.length) startAlarm(); else stopAlarm();
    return stopAlarm;
  }, [alarms.length]);

  if (!alarms.length) return null;

  async function confirmAll() {
    setBusy(true);
    try { await Promise.all(alarms.map((a) => api.confirm(a.id))); setAlarms([]); }
    finally { setBusy(false); }
  }

  return (
    <div className="alarm" role="alertdialog" aria-modal="true" aria-labelledby="alarm-title">
      <h2 id="alarm-title">{t("alarmTitle")}</h2>
      <p className="alarm-time">{alarms[0].time_local}</p>
      <ul>
        {alarms.map((a) => (
          <li key={a.id}>
            <strong>{a.med_name} {a.strength}</strong>
            <span>{a.quantity} {a.quantity === 1 ? "tablet" : "tablets"}</span>
            {a.instructions && <em>{a.instructions}</em>}
          </li>
        ))}
      </ul>
      <button className="took" onClick={confirmAll} disabled={busy}>{t("tookIt")}</button>
      <p className="fine">If you do not confirm, MedLens will call your phone.</p>
    </div>
  );
}
