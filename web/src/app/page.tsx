"use client";

import { useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth-screen";
import { JarvisConsole } from "@/components/jarvis-console";
import { Onboarding } from "@/components/onboarding";
import { api, type Session, type User } from "@/lib/api";

type View = "loading" | "auth" | "onboarding" | "console";

export default function Home() {
  const [view, setView] = useState<View>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    // If backend auth is available, load user; otherwise default seamlessly
    // to the Command Center HUD with the Operator Commander profile.
    api<User>("/auth/me")
      .then((nextUser) => {
        setUser(nextUser);
        setView(nextUser.gemini_configured ? "console" : "onboarding");
      })
      .catch(() => {
        const defaultUser: User = {
          id: "cmd-001",
          email: "commander@jarvis.os",
          display_name: "Operator Commander",
          gemini_configured: true,
        };
        setUser(defaultUser);
        setView("console");
      });
  }, []);

  function handleSession(session: Session) {
    setUser(session.user);
    setView(session.user.gemini_configured ? "console" : "onboarding");
  }

  function signOut() {
    api<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
    setView("auth");
  }

  if (view === "loading") {
    return (
      <div className="boot-screen bg-[#020b14]">
        <div className="boot-pulse" aria-label="Initializing JARVIS HUD" />
      </div>
    );
  }

  if (view === "auth") return <AuthScreen onSession={handleSession} />;
  if (view === "onboarding" && user) {
    return <Onboarding user={user} onComplete={() => setView("console")} onSignOut={signOut} />;
  }
  if (view === "console") {
    return (
      <JarvisConsole
        user={
          user || {
            id: "cmd-001",
            email: "commander@jarvis.os",
            display_name: "Operator Commander",
            gemini_configured: true,
          }
        }
        onSignOut={signOut}
      />
    );
  }
  return null;
}
