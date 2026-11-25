import { useEffect, useState } from "react";
import "./StatusBar.css";

const timeFmt = new Intl.DateTimeFormat("ro-RO", {
 hour: "2-digit",
 minute: "2-digit",
 hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("ro-RO", {
 weekday: "long",
 day: "numeric",
 month: "long",
});

const HEALTH_POLL_MS = 10000;

function useClock() {
 const [now, setNow] = useState(() => new Date());
 useEffect(() => {
  const id = setInterval(() => setNow(new Date()), 1000);
  return () => clearInterval(id);
 }, []);
 return now;
}

function useHealth() {
 const [health, setHealth] = useState(null);

 useEffect(() => {
  let cancelled = false;

  async function load() {
   try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!cancelled) setHealth(data);
   } catch {
    if (!cancelled) setHealth((prev) => ({ ...prev, online: false }));
   }
  }

  load();
  const id = setInterval(load, HEALTH_POLL_MS);
  return () => {
   cancelled = true;
   clearInterval(id);
  };
 }, []);

 return health;
}

function GearIcon() {
 return (
  <svg
   width="24"
   height="24"
   viewBox="0 0 24 24"
   fill="none"
   stroke="currentColor"
   strokeWidth="2"
   strokeLinecap="round"
   strokeLinejoin="round"
   aria-hidden="true"
  >
   <circle cx="12" cy="12" r="3" />
   <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </svg>
 );
}

function LockIcon({ locked }) {
 return (
  <svg
   width="24"
   height="24"
   viewBox="0 0 24 24"
   fill="none"
   stroke="currentColor"
   strokeWidth="2"
   strokeLinecap="round"
   strokeLinejoin="round"
   aria-hidden="true"
  >
   <rect x="4" y="11" width="16" height="10" rx="2" />
   <path d={locked ? "M8 11V7a4 4 0 0 1 8 0v4" : "M8 11V7a4 4 0 0 1 7.5-2"} />
  </svg>
 );
}

export default function StatusBar({
 locked = true,
 onSettingsClick,
 onLockClick,
}) {
 const now = useClock();
 const health = useHealth();

 const state =
  health == null ? "unknown" : health.online ? "online" : "offline";
 const stateText = {
  unknown: "Se verifică…",
  online: "Online",
  offline: "Offline",
 }[state];

 return (
  <div className="status-bar">
   <span className="status-bar__clock">{timeFmt.format(now)}</span>
   <span className="status-bar__date">{dateFmt.format(now)}</span>

   <span className="status-bar__divider" aria-hidden="true" />

   <span
    className={`status-bar__conn status-bar__conn--${state}`}
    role="status"
   >
    <span className="status-bar__dot" aria-hidden="true" />
    {stateText}
   </span>

   {health?.mail_mode === "mock" && (
    <span className="status-bar__badge">Mock</span>
   )}

   <div className="status-bar__actions">
    <button
     type="button"
     className="touch-target status-bar__btn"
     aria-label="Setări"
     onClick={onSettingsClick}
    >
     <GearIcon />
    </button>
    <button
     type="button"
     className="touch-target status-bar__btn"
     aria-label={locked ? "Deblochează" : "Blochează"}
     onClick={onLockClick}
    >
     <LockIcon locked={locked} />
    </button>
   </div>
  </div>
 );
}
