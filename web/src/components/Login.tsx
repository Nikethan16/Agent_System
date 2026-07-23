import { useState } from "react";
import { api, setAuthToken, ApiError } from "../lib/api";
import Sunburst from "./Sunburst";

// Email + password gate shown before the app loads (when login is enabled on the
// server). On success it stores the auth token the rest of the app uses.
export default function Login({ onSuccess }: { onSuccess: (email: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setErr(""); setBusy(true);
    try {
      const r = await api.login(email, password);
      setAuthToken(r.token || "");
      onSuccess(r.email || email);
    } catch (e: any) {
      setErr(e instanceof ApiError && e.status === 401 ? "Invalid email or password." : (e?.message || "Sign in failed."));
      setBusy(false);
    }
  };

  const inp = "w-full bg-surface-container-low dark:bg-dark-bg border border-light-border dark:border-dark-border rounded-xl px-3.5 py-2.5 text-[15px] outline-none focus:border-accent-terracotta/50 transition";

  return (
    <div className="h-screen flex items-center justify-center bg-surface dark:bg-dark-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <Sunburst size={40} />
          <h1 className="font-headline text-xl font-semibold mt-3">Nikki</h1>
          <p className="text-light-muted text-sm mt-1">Sign in to continue</p>
        </div>
        <form onSubmit={submit} className="bg-white dark:bg-dark-surface border border-light-border dark:border-dark-border rounded-2xl shadow-sm p-6 space-y-4">
          <div>
            <label className="text-xs text-light-muted">Email</label>
            <input type="email" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} className={inp + " mt-1"} placeholder="you@example.com" />
          </div>
          <div>
            <label className="text-xs text-light-muted">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={inp + " mt-1"} placeholder="••••••••" />
          </div>
          {err && <p className="text-xs text-red-500">{err}</p>}
          <button type="submit" disabled={busy || !email || !password}
            className="w-full py-2.5 bg-accent-terracotta hover:bg-accent-deep text-white font-medium rounded-xl transition active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-accent-terracotta">
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="text-center text-[11px] text-light-muted mt-4">Private instance · authorized access only</p>
      </div>
    </div>
  );
}
