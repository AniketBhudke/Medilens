import { useState } from "react";
import { api } from "../api";

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function changeMode(next) {
    setMode(next);
    setMessage("");
    setError("");
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);
    try {
      if (mode === "signup") {
        await api.signup({ name, phone, password });
        setMode("verify");
        setMessage("Enter the 6-digit code sent to your phone. In mock mode, check the backend console.");
      } else if (mode === "verify") {
        onAuthenticated(await api.verifyPhone({ phone, code }));
      } else if (mode === "forgot") {
        const result = await api.forgotPassword({ phone });
        setMode("reset");
        setMessage(`${result.message} In mock mode, check the backend console.`);
      } else if (mode === "reset") {
        const result = await api.resetPassword({ phone, code, new_password: newPassword });
        setMode("login");
        setPassword("");
        setCode("");
        setNewPassword("");
        setMessage(result.message);
      } else {
        onAuthenticated(await api.login({ phone, password }));
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setError("");
    setMessage("");
    try {
      const purpose = mode === "verify" ? "signup" : "reset";
      const result = await api.resendCode({ phone, purpose });
      setMessage(`${result.message} In mock mode, check the backend console.`);
    } catch (e) {
      setError(e.message);
    }
  }

  const showPassword = mode === "login" || mode === "signup";
  const showCode = mode === "verify" || mode === "reset";

  return (
    <main className="auth">
      <h1>MedLens</h1>
      <form className="card form" onSubmit={submit}>
        <h2>{mode === "signup" ? "Create your account" : mode === "verify" ? "Verify your phone" : mode === "forgot" ? "Forgot password" : mode === "reset" ? "Reset password" : "Sign in"}</h2>
        {mode === "signup" && (
          <label>Name
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength="100" />
          </label>
        )}
        <label>Mobile number
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919876543210"
                 inputMode="tel" autoComplete="tel" required pattern="^\+\d{8,15}$" disabled={mode === "verify" || mode === "reset"} />
        </label>
        {showPassword && (
          <label>Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete={mode === "signup" ? "new-password" : "current-password"}
                   minLength={mode === "signup" ? 8 : 1} maxLength="128" required />
          </label>
        )}
        {showCode && (
          <label>6-digit SMS code
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric"
                   autoComplete="one-time-code" pattern="\d{6}" maxLength="6" required />
          </label>
        )}
        {mode === "reset" && (
          <label>New password
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                   autoComplete="new-password" minLength="8" maxLength="128" required />
          </label>
        )}

        {message && <div className="banner info" role="status">{message}</div>}
        {error && <div className="banner danger" role="alert">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? "Please wait…" : mode === "signup" ? "Create account" : mode === "verify" ? "Verify and continue" : mode === "forgot" ? "Send reset code" : mode === "reset" ? "Set new password" : "Sign in"}</button>

        {mode === "login" && (
          <div className="auth-links">
            <button type="button" className="link" onClick={() => changeMode("forgot")}>Forgot password?</button>
            <button type="button" className="link" onClick={() => changeMode("signup")}>Create an account</button>
          </div>
        )}
        {(mode === "verify" || mode === "reset") && (
          <div className="auth-links">
            <button type="button" className="link" onClick={resendCode}>Resend code</button>
            <button type="button" className="link" onClick={() => changeMode("login")}>Back to sign in</button>
          </div>
        )}
        {(mode === "signup" || mode === "forgot") && (
          <button type="button" className="link" onClick={() => changeMode("login")}>Back to sign in</button>
        )}
        <p className="fine">Use your full phone number with country code. SMS verification and password recovery require Twilio to be configured; without it, codes appear in the backend console for local testing.</p>
      </form>
    </main>
  );
}
