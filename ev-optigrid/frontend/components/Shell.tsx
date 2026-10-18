"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "@/components/AuthProvider";

const NAV = [
  { group: "Plan", items: [
    { href: "/", label: "Overview" },
    { href: "/smart-charging", label: "Smart charging" },
    { href: "/journey", label: "Journey planner" },
    { href: "/stations", label: "Charging stations" },
    { href: "/copilot", label: "Copilot" },
    { href: "/fleet", label: "Fleet dashboard" },
  ] },
  { group: "Simulate", items: [
    { href: "/twin", label: "Digital twin" },
    { href: "/simulator", label: "Policy simulator" },
    { href: "/battery", label: "Battery health" },
  ] },
  { group: "How it decides", items: [
    { href: "/optimiser/state-space", label: "State space" },
    { href: "/optimiser/policy", label: "Policy heatmap" },
    { href: "/optimiser/bellman", label: "Bellman equation" },
    { href: "/optimiser/monte-carlo", label: "Monte Carlo" },
    { href: "/optimiser/sensitivity", label: "Sensitivity" },
  ] },
];

type Health = { state: "checking" } | { state: "down" } | { state: "up"; demo: boolean };

function BackendStatus() {
  const [health, setHealth] = useState<Health>({ state: "checking" });
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const res = await fetch("/backend-health");
        const body = await res.json();
        if (alive) setHealth(res.ok ? { state: "up", demo: Boolean(body.demo_mode) } : { state: "down" });
      } catch {
        if (alive) setHealth({ state: "down" });
      }
    };
    check();
    const t = setInterval(check, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const text = health.state === "up" ? "Backend connected" : health.state === "down" ? "Backend offline" : "Checking backend";
  const sub = health.state === "up" ? (health.demo ? "Using demo data" : "Using live providers")
    : health.state === "down" ? "Run: uvicorn main:app" : "";
  return (
    <div className="backend-status" role="status">
      <span className={`dot ${health.state === "up" ? "ok" : health.state === "down" ? "bad" : ""}`} />
      <span>{text}</span>
      {sub && <small>{sub}</small>}
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { status, user, signOut } = useAuth();
  const onLoginPage = pathname === "/login";

  // Route guard: everything except /login needs a session.
  useEffect(() => {
    if (status === "anonymous" && !onLoginPage) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, onLoginPage, pathname, router]);

  if (onLoginPage) return <>{children}</>;
  if (status !== "authenticated") return <div className="boot" role="status">Loading</div>;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark" aria-hidden>⚡</span>EV-OptiGrid</div>
        <nav aria-label="Main" style={{ display: "contents" }}>
          {NAV.map((g) => (
            <div className="nav-group" key={g.group}>
              <h2>{g.group}</h2>
              {g.items.map((i) => (
                <Link key={i.href} href={i.href} className="nav-link"
                  aria-current={pathname === i.href ? "page" : undefined}>{i.label}</Link>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <BackendStatus />
          <div className="account">
            <div>
              <strong>{user?.name}</strong>
              <small>{user?.email.startsWith("demo-") ? "Demo account" : user?.email}</small>
            </div>
            <button className="btn ghost small" onClick={() => { signOut(); router.replace("/login"); }}>Sign out</button>
          </div>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
