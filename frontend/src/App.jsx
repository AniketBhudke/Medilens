import { useEffect, useState } from "react";
import { api } from "./api";
import { useT } from "./i18n";
import { unlockAudio } from "./sound";
import ScanPage from "./components/ScanPage.jsx";
import SchedulePage from "./components/SchedulePage.jsx";
import SettingsPage from "./components/SettingsPage.jsx";
import AlarmOverlay from "./components/AlarmOverlay.jsx";
import AuthPage from "./components/AuthPage.jsx";
import Chatbot from "./components/Chatbot.jsx";

export default function App() {
  const [profile, setProfile] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [tab, setTab] = useState("scan");
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);
  const t = useT(profile?.language || "en");

  useEffect(() => {
    const unlock = () => unlockAudio();
    window.addEventListener("pointerdown", unlock, { once: true });
    api.health().then(setHealth).catch(() => setError("Cannot reach the MedLens server. Start the backend on port 8000."));
    (async () => {
      if (api.hasAuthToken()) {
        try {
          setProfile(await api.me());
        } catch {
          api.clearAuthToken();
        }
      }
      setAuthReady(true);
    })();
  }, []);

  if (!authReady) return <div className="boot">{error || "Loading MedLens…"}</div>;
  if (!profile) return <>{error && <div className="banner danger" role="alert">{error}</div>}<AuthPage onAuthenticated={setProfile} /></>;

  async function logout() {
    try { await api.logout(); }
    catch (e) { setError(e.message); }
    setProfile(null);
  }

  return (
    <div className="app">
      <header className="top">
        <h1>MedLens</h1>
        {health && (health.ai === "demo" || health.calls === "mock") && (
          <span className="chip">{[health.ai === "demo" && "AI demo", health.calls === "mock" && "calls mocked"].filter(Boolean).join(" · ")}</span>
        )}
      </header>
      {error && <div className="banner danger" role="alert">{error}</div>}

      <main>
        {tab === "scan" && <ScanPage profile={profile} onPlanCreated={() => setTab("today")} />}
        {tab === "today" && <SchedulePage profile={profile} demo={health?.demo_mode} />}
        {tab === "settings" && <SettingsPage profile={profile} onSaved={setProfile} onLogout={logout} />}
      </main>

      <nav className="tabs" aria-label="Main">
        {["scan", "today", "settings"].map((k) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)} aria-current={tab === k}>{t(k)}</button>
        ))}
      </nav>

      <Chatbot />
      <AlarmOverlay profile={profile} />
    </div>
  );
}
