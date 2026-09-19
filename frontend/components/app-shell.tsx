"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";

const navigation = [
  ["/dashboard", "Dashboard", "⌁"],
  ["/live", "Live", "◉"],
  ["/review", "Review", "✓"],
  ["/creators", "Creators", "◎"],
  ["/posts", "Posts", "▱"],
  ["/comments", "Comments", "◌"],
  ["/campaigns", "Campaigns", "⌖"],
  ["/brand", "Brand", "◇"],
  ["/accounts", "Accounts", "▣"],
  ["/risk", "Risk", "△"],
  ["/analytics", "Analytics", "↗"],
  ["/settings", "Settings", "⚙"],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user && pathname !== "/login") router.replace("/login");
  }, [loading, user, pathname, router]);

  if (pathname === "/login") return <>{children}</>;
  if (loading || !user) return <main className="main-content" role="status">Checking session…</main>;

  const signOut = () => {
    logout();
    router.push("/login");
  };

  return (
    <div className="app-frame">
      <button
        className="mobile-menu"
        aria-label="Toggle navigation"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen((value) => !value)}
      >
        ☰
      </button>
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <Link href="/dashboard" className="brand-lockup" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark">FC</span>
          <span>
            <strong>FirstComment</strong>
            <small>Agent Console</small>
          </span>
        </Link>
        <nav aria-label="Main navigation">
          {navigation.map(([href, label, icon]) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={active ? "nav-link active" : "nav-link"}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <span aria-hidden="true">{icon}</span>
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="environment-pill">
            <span /> Development
          </div>
          <div className="user-row">
            <div className="avatar">{user?.email.slice(0, 1).toUpperCase() ?? "?"}</div>
            <div>
              <strong>
                {loading
                  ? "Checking session…"
                  : user?.display_name ?? user?.email ?? "Not signed in"}
              </strong>
              <small>{user?.role ?? "VIEWER"}</small>
            </div>
          </div>
          {user ? (
            <button className="text-button" onClick={signOut}>
              Sign out
            </button>
          ) : (
            <Link href="/login" className="text-button">
              Sign in
            </Link>
          )}
        </div>
      </aside>
      {mobileOpen ? <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} /> : null}
      <main className="main-content">{children}</main>
    </div>
  );
}
