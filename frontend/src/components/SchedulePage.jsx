import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";

const SLOTS = ["morning", "afternoon", "evening", "night"];

export default function SchedulePage({ profile, demo }) {
  const t = useT(profile.language);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => api.schedule(profile.id).then(setData).catch((e) => setError(e.message)), [profile.id]);
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  const confirm = async (id) => { try { await api.confirm(id); load(); } catch (e) { setError(e.message); } };
  const fire = async (id) => { try { await api.fire(id); load(); } catch (e) { setError(e.message); } };

  if (!data) return <p className="fine">{error || "Loading…"}</p>;
  const statusLabel = { taken: t("taken"), missed: t("missed"), pending: t("due"), alarming: t("ringing") };

  return (
    <section>
      <div className="progress" aria-label={`${data.taken} of ${data.total} taken`}>
        <div style={{ width: data.total ? `${(100 * data.taken) / data.total}%` : 0 }} />
        <span>{data.taken} / {data.total}</span>
      </div>
      {error && <div className="banner danger">{error}</div>}
      {data.total === 0 && <p className="empty">{t("noDoses")}</p>}

      {SLOTS.filter((s) => data.slots[s].length).map((s) => (
        <div key={s} className="slot">
          <h2>{t(s)}</h2>
          {data.slots[s].map((d) => (
            <article key={d.id} className={`card dose ${d.status}`}>
              <div>
                <h3>{d.med_name} <small>{d.strength}</small></h3>
                <p>{d.time_local} · {d.quantity} {d.quantity === 1 ? "tablet" : "tablets"}</p>
                {d.instructions && <p className="how">{d.instructions}</p>}
                {d.call_at && d.status !== "taken" && <p className="fine">Reminder call placed{d.caregiver_at ? "; caregiver notified" : ""}.</p>}
              </div>
              <div className="actions">
                <span className={`pill ${d.status}`}>{statusLabel[d.status]}</span>
                {d.status !== "taken" && (d.status !== "pending" || new Date(d.scheduled_at).getTime() <= Date.now()) &&
                  <button className="primary small" onClick={() => confirm(d.id)}>{t("tookIt")}</button>}
                {demo && d.status === "pending" && <button className="link" onClick={() => fire(d.id)}>Test alarm now</button>}
              </div>
            </article>
          ))}
        </div>
      ))}
    </section>
  );
}
