"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const DEMO = [
  { email: "commander@disha.demo", role: "Commander", note: "Events, priority, resources, routes, reports" },
  { email: "analyst@disha.demo", role: "Analyst", note: "Satellite, AI, change detection, data" },
  { email: "responder@disha.demo", role: "Field responder", note: "Missions, navigation, photos, status" },
  { email: "observer@disha.demo", role: "Observer", note: "Read-only" },
  { email: "admin@disha.demo", role: "Admin", note: "Full access" },
];

export default function Login() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("commander@disha.demo");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email, password);
      router.replace("/command-center");
    } catch (ex: any) {
      setErr(ex.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-ink p-4">
      <div className="grid w-full max-w-4xl gap-6 md:grid-cols-2">
        <section className="flex flex-col justify-center">
          <div className="text-4xl font-bold text-strong">DISHA</div>
          <div className="mt-1 text-sm text-muted">Disaster Intelligence, Situational Hazard Assessment and Response Orchestration</div>
          <p className="mt-6 text-lg font-semibold text-strong">From satellite images to a clear answer on where to respond first.</p>
          <p className="mt-2 text-sm text-text">DISHA compares satellite images from before and after a disaster, combines them with population, roads and hospitals, and ranks which areas need help first, with the reasons shown.</p>
          <div className="mt-6 rounded-md border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
            Prototype for evaluation. Not an operational emergency system. Events labelled &ldquo;Simulated&rdquo; use generated data; events labelled &ldquo;Real data&rdquo; use open satellite and map data with the limitations described in the Guide.
          </div>
        </section>
        <section className="panel p-5">
          <h1 className="mb-4 text-sm font-bold   text-muted">Sign in</h1>
          <form onSubmit={submit} className="space-y-3">
            <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
            <div><label className="label" htmlFor="pw">Password</label><input id="pw" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
            {err && <div className="rounded border border-p1/50 bg-p1/10 px-3 py-2 text-xs text-p1">{err}</div>}
            <button className="btn btn-primary w-full" disabled={busy || !password}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
          <div className="mt-5 border-t border-line pt-3">
            <div className="mb-2 text-[11px] font-bold   text-warn">Demo accounts (password: Disha@2026)</div>
            <ul className="space-y-1">
              {DEMO.map((d) => (
                <li key={d.email}>
                  <button type="button" onClick={() => { setEmail(d.email); setPassword("Disha@2026"); }} className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-panel2">
                    <span className="tabular-nums text-text">{d.email}</span><span className="text-[11px] text-muted">{d.role}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </main>
  );
}
