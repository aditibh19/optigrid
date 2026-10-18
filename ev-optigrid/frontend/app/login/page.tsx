"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { Notice, TextField, errorMessage } from "@/components/ui";

type Mode = "signin" | "signup";

/** Only allow same-site relative paths, so a crafted ?next= can't bounce users to another site. */
function safeNext(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export default function LoginPage() {
  const router = useRouter();
  const { status, signIn, signUp, startDemo } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (status === "authenticated") router.replace(safeNext()); }, [status, router]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); router.replace(safeNext()); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  const canSubmit = email.includes("@") && password.length >= 8 && (mode === "signin" || name.trim().length > 0);

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand" style={{ padding: 0, marginBottom: 6 }}><span className="brand-mark" aria-hidden>⚡</span>EV-OptiGrid</div>
        <h1>{mode === "signin" ? "Sign in" : "Create your account"}</h1>
        <p className="login-lede">Charging decisions that weigh price, grid load, your battery and your trip, with the reasons shown.</p>

        <div className="tabs" role="tablist" aria-label="Account">
          <button role="tab" aria-selected={mode === "signin"} className="tab" onClick={() => { setMode("signin"); setError(null); }}>Sign in</button>
          <button role="tab" aria-selected={mode === "signup"} className="tab" onClick={() => { setMode("signup"); setError(null); }}>Create account</button>
        </div>

        <form className="stack" onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) void run(() => (mode === "signin" ? signIn(email.trim(), password) : signUp(name.trim(), email.trim(), password)));
        }}>
          {mode === "signup" && <TextField label="Your name" value={name} onChange={setName} />}
          <TextField label="Email" value={email} onChange={setEmail} />
          <div className="field">
            <label htmlFor="pw">Password</label>
            <div className="input-wrap">
              <input id="pw" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {mode === "signup" && <span className="hint">At least 8 characters.</span>}
          </div>
          {error && <Notice tone="error">{error}</Notice>}
          <button className="btn" type="submit" disabled={busy || !canSubmit}>
            {busy ? "Please wait" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>

        <div className="login-divider"><span>or</span></div>
        <button className="btn ghost" disabled={busy} onClick={() => void run(startDemo)}>Explore with a demo account</button>
        <p className="hint" style={{ marginTop: 10, fontSize: 12, color: "var(--text-muted)" }}>
          Creates a temporary account on this backend, so no email is needed. Data is not personal and may be reset.
        </p>
      </div>
    </div>
  );
}
