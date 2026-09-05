"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore, type ReactNode } from "react";

const clinicalNavigation = [
  { href: "/dashboard", label: "Overview", icon: "overview" },
  { href: "/patients", label: "Patients", icon: "patients" },
  { href: "/admissions", label: "Admissions", icon: "admissions" },
  { href: "/requests/new", label: "Requests", icon: "requests" },
  { href: "/profile", label: "Profile", icon: "profile" },
] as const;

const bankNavigation = [
  { href: "/bank", label: "Overview", icon: "overview" },
  { href: "/bank/inventory", label: "Inventory", icon: "admissions" },
  { href: "/bank/requests", label: "Requests", icon: "requests" },
  { href: "/bank/demand", label: "Donors", icon: "patients" },
  { href: "/bank/settings", label: "Settings", icon: "profile" },
];

export function AppIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    patients: <><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3" /></>,
    admissions: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 7h6M9 11h6M9 15h2m4 2v4" /></>,
    requests: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5" /></>,
    profile: <><circle cx="12" cy="8" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3" /></>,
    drop: <path d="M12 3C10 6 5 11 5 15a7 7 0 0 0 14 0c0-4-5-9-7-12Z" />,
  };
  return <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.requests}</svg>;
}

function Brand() {
  return <Link href="/" className="brand" aria-label="Blood Request home"><span className="brand-mark"><AppIcon name="drop" /></span><span className="brand-copy"><span className="brand-title">Blood Request</span><span className="brand-subtitle">Clinical workspace</span></span></Link>;
}

function subscribeNetwork(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isBank = pathname.startsWith("/bank");
  const navigation = isBank ? bankNavigation : clinicalNavigation;
  const isClinical = ["/dashboard", "/patients", "/admissions", "/requests", "/profile", "/admin", "/bank"].some(
    (route) => pathname === route || pathname.startsWith(`${route}/`)
  );
  const online = useSyncExternalStore(subscribeNetwork, () => navigator.onLine, () => true);

  return (
    <div className={`app-shell${isClinical ? " clinical-shell" : ""}`}>
      <a href="#main-content" className="skip-link">Skip to content</a>
      {isClinical && <nav className="app-nav" aria-label="Main navigation">
        <div className="nav-brand"><Brand /></div>
        {navigation.map(({ href, label, icon }) => {
          const base = href === "/requests/new" ? "/requests" : href;
          const active = pathname === base || pathname.startsWith(`${base}/`);
          return <Link key={href} href={href} className="nav-link" aria-current={active ? "page" : undefined} title={label}><AppIcon name={icon} /><span className="nav-label">{label}</span></Link>;
        })}
        <div className="nav-footer">Hospital workflow trial<br />Institutional validation required</div>
      </nav>}
      <div className="workspace-content">
        <header className="app-topbar">
          {isClinical ? <span className="brand"><AppIcon name="requests" /><span className="brand-copy"><span className="brand-title">{isBank ? "Blood bank" : "Clinical workspace"}</span><span className="brand-subtitle">{isBank ? "Stock, requests and donor recruitment" : "Blood request management"}</span></span></span> : <Brand />}
          <div className="topbar-meta"><span className="trial-label">Hospital use trial</span>{isClinical ? <><span className={isBank ? "role-badge role-bank" : "role-badge role-doctor"}>{isBank ? "Blood bank" : "Clinical team"}</span><form method="post" action="/api/auth/sign-out" className="inline-form"><button type="submit" className="button">Sign out</button></form></> : <Link className="button" href="/sign-in">Sign in</Link>}</div>
        </header>
        {!online && <div className="notice notice-offline network-banner" role="status">You’re offline. Clinical data and all changes require a network connection. Reconnect before continuing.</div>}
        {children}
        <footer className="medical-disclaimer">
          <strong>For institutional evaluation only</strong>
          <p>This software is provided AS IS, is not medical advice, and is not a substitute for clinical judgment. It is not clinically validated and must not be used in a real clinical environment without validation, security review, compliance review, and institutional authorization.</p>
        </footer>
      </div>
    </div>
  );
}