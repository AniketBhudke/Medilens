const BASE = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "medlens_auth_token";
let authToken = localStorage.getItem(TOKEN_KEY) || "";

export function setAuthToken(token) {
  authToken = token || "";
  if (authToken) localStorage.setItem(TOKEN_KEY, authToken);
  else localStorage.removeItem(TOKEN_KEY);
}

async function req(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  const res = await fetch(BASE + path, { ...opts, headers });
  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return body;
}
const json = (method, data) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

export const api = {
  health: () => req("/api/health"),
  chat: (messages) => req("/api/chat", json("POST", { messages })),
  hasAuthToken: () => Boolean(authToken),
  clearAuthToken: () => setAuthToken(""),
  async signup(data) { return req("/api/auth/signup", json("POST", data)); },
  async verifyPhone(data) {
    const result = await req("/api/auth/verify-phone", json("POST", data));
    setAuthToken(result.token);
    return result.profile;
  },
  async login(data) {
    const result = await req("/api/auth/login", json("POST", data));
    setAuthToken(result.token);
    return result.profile;
  },
  forgotPassword: (data) => req("/api/auth/forgot-password", json("POST", data)),
  resetPassword: (data) => req("/api/auth/reset-password", json("POST", data)),
  resendCode: (data) => req("/api/auth/resend-code", json("POST", data)),
  me: () => req("/api/auth/me"),
  async logout() {
    try { await req("/api/auth/logout", { method: "POST" }); }
    finally { setAuthToken(""); }
  },
  analyze(file, language, sex, force = false) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("language", language);
    fd.append("sex", sex);
    fd.append("force", force ? "true" : "false");
    return req("/api/analyze", { method: "POST", body: fd });
  },
  getProfile: (id) => req(`/api/profiles/${id}`),
  updateProfile: (id, p) => req(`/api/profiles/${id}`, json("PUT", p)),
  createPlan: (id, plan) => req(`/api/profiles/${id}/plan`, json("POST", plan)),
  schedule: (id) => req(`/api/profiles/${id}/schedule`),
  alarms: (id) => req(`/api/profiles/${id}/alarms`),
  confirm: (doseId) => req(`/api/doses/${doseId}/confirm`, { method: "POST" }),
  fire: (doseId) => req(`/api/doses/${doseId}/fire`, { method: "POST" }),
};
