"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { Spinner } from "./ui";

const ICONS: Record<string, JSX.Element> = {
  guide: <path d="M12 17v.01M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7" />,
  command: <path d="M4 5h16v10H4zM9 19h6M12 15v4" />,
  dashboard: <path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z" />,
  events: <path d="M5 21V4m0 0h11l-2 4 2 4H5" />,
  copilot: <path d="M4 5h16v11H9l-5 4z" />,
  settings: <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M6 15v4" />,
  admin: <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />,
};
function Icon({ name }: { name: string }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{ICONS[name]}</svg>;
}

const NAV = [
  { href: "/guide", label: "Guide", icon: "guide" },
  { href: "/command-center", label: "Command Centre", icon: "command" },
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/events", label: "Events", icon: "events" },
  { href: "/copilot", label: "Copilot", icon: "copilot" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const presenting = path?.endsWith("/present");

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) return <Spinner text="Authenticating…" />;
  if (presenting) return <>{children}</>;
  const items = user.role === "admin" ? [...NAV, { href: "/admin", label: "Admin", icon: "admin" }] : NAV;
  return (
    <div className="flex h-screen flex-col">
      <header className="flex h-11 shrink-0 items-center justify-between border-b border-line bg-panel px-4">
        <div className="flex items-baseline gap-3">
          <span className="tabular-nums text-lg font-bold  text-strong">DISHA</span>
          <span className="hidden text-xs text-muted md:inline">Disaster response decision support</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="hidden rounded border border-line px-2 py-0.5 text-xs text-muted md:inline">Prototype</span>
          <span className="text-muted">{user.name} · <span className="font-semibold  text-text">{user.role}</span></span>
          <button className="btn btn-sm" onClick={logout}>Sign out</button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav className="flex w-14 shrink-0 flex-col items-stretch border-r border-line bg-panel md:w-44">
          {items.map((n) => {
            const active = path === n.href || path?.startsWith(n.href + "/");
            return (
              <Link key={n.href} href={n.href} className={`flex items-center gap-3 px-4 py-2.5 text-xs font-semibold   ${active ? "border-l-2 border-accent bg-panel2 text-strong" : "border-l-2 border-transparent text-muted hover:text-text"}`}>
                <Icon name={n.icon} /><span className="hidden md:inline">{n.label}</span>
              </Link>
            );
          })}
        </nav>
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
