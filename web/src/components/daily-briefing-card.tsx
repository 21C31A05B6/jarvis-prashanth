"use client";

import { useEffect, useState } from "react";
import { Sun } from "lucide-react";
import { api, type DailyBriefing } from "@/lib/api";

export function DailyBriefingCard() {
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null);

  useEffect(() => {
    api<DailyBriefing>("/daily-briefing").then(setBriefing).catch(() => undefined);
  }, []);

  if (!briefing) return null;

  return (
    <section className="agent-panel" aria-labelledby="briefing-title">
      <div className="capability-heading">
        <span id="briefing-title"><Sun size={12} style={{ marginRight: 6, display: "inline" }} />Daily briefing</span>
      </div>
      <p className="agent-empty" style={{ padding: "0 1.2rem .8rem" }}>{briefing.greeting}</p>
    </section>
  );
}
