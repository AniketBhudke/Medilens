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

const PAGE_COPY = {
  scan: {
    title: "Prescription review",
    description: "Upload a prescription to review medicines and organize reminders.",
  },
  today: {
    title: "Today’s schedule",
    description: "Keep track of today’s doses and confirm them after you take them.",
  },
  settings: {
    title: "Your preferences",
    description: "Manage your account, reminder times and care notifications.",
  },
};

function NavIcon({ name }) {
  const paths = {
    scan: <><path d="M7 3.75h7l4 4v12.5H7z" /><path d="M14 3.75v4h4M10 12h5M10 15.5h5" /></>,
    today: <><rect x="4" y="5.5" width="16" height="15" rx="2" /><path d="M8 3.5v4M16 3.5v4M4 9.5h16M8 14l2.2 2.2L16 11.5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.6.9l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.6-.9l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.9l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.6-.9l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.6.9l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.9Z" transform="translate(-1 -1)" /></>,
  };

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

function Navigation({ tab, setTab, t, className }) {
  return (
    <nav className={className} aria-label="Main navigation">
      {["scan", "today", "settings"].map((key) => (
        <button key={key} type="button" className={tab === key ? "on" : ""}
                onClick={() => setTab(key)} aria-current={tab === key ? "page" : undefined}>
          <NavIcon name={key} />
          <span>{t(key)}</span>
        </button>
      ))}
    </nav>
  );
}

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

  const page = PAGE_COPY[tab];
  const initials = (profile.name?.trim()?.charAt(0) || "M").toUpperCase();

  return (
    <div className="app">
      <div className="app-shell">
        <aside className="sidebar">
          <a className="brand" href="#" aria-label="MedLens home" onClick={(event) => { event.preventDefault(); setTab("scan"); }}>
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none">
                <rect x="1" y="1" width="30" height="30" rx="10" fill="currentColor" />
                <path d="M16 8v16M8 16h16" stroke="white" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </span>
            <span className="brand-name">MedLens<small>PERSONAL CARE</small></span>
          </a>
          <p className="sidebar-label">WORKSPACE</p>
          <Navigation tab={tab} setTab={setTab} t={t} className="sidebar-nav" />
          <div className="sidebar-note">
            <span className="note-icon" aria-hidden="true">i</span>
            <strong>A little support, every day</strong>
            <p>Keep your health information and medication routine organized in one place.</p>
          </div>
          <div className="sidebar-profile">
            <span className="avatar">{initials}</span>
            <span><strong>{profile.name || "Your account"}</strong><small>Personal account</small></span>
          </div>
        </aside>

        <div className="workspace">
          <header className="top">
            <div className="mobile-brand">
              <span className="brand-mark" aria-hidden="true">
                <svg viewBox="0 0 32 32" fill="none">
                  <rect x="1" y="1" width="30" height="30" rx="10" fill="currentColor" />
                  <path d="M16 8v16M8 16h16" stroke="white" strokeWidth="3" strokeLinecap="round" />
                </svg>
              </span>
              <strong>MedLens</strong>
            </div>
            <div className="top-status">
              <span className="status-dot" aria-hidden="true" />
              <span>Private health workspace</span>
            </div>
            <div className="top-user">
              <span className="avatar">{initials}</span>
              <span>{profile.name || "Your account"}</span>
            </div>
          </header>

          {error && <div className="banner danger global-error" role="alert">{error}</div>}

          <main className="content">
            <section className="page-heading" aria-labelledby="page-title">
              <div>
                <p className="eyebrow">YOUR HEALTH, AT A GLANCE</p>
                <h1 id="page-title">{page.title}</h1>
                <p>{page.description}</p>
              </div>
              {health && (health.ai === "demo" || health.calls === "mock") && (
                <span className="chip">
                  {[health.ai === "demo" && "AI demo", health.calls === "mock" && "Calls mocked"].filter(Boolean).join(" · ")}
                </span>
              )}
            </section>

            {tab === "scan" && <ScanPage profile={profile} onPlanCreated={() => setTab("today")} />}
            {tab === "today" && <SchedulePage profile={profile} demo={health?.demo_mode} />}
            {tab === "settings" && <SettingsPage profile={profile} onSaved={setProfile} onLogout={logout} />}

            <footer className="safety-note">
              <span aria-hidden="true">✚</span>
              <p>MedLens helps you organize health information. It does not replace advice from your doctor or pharmacist.</p>
            </footer>
          </main>
        </div>
      </div>

      <Navigation tab={tab} setTab={setTab} t={t} className="tabs" />

      <Chatbot />
      <AlarmOverlay profile={profile} />
    </div>
  );
}
