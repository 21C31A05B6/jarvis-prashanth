"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ArrowUp, ListChecks } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Agent, type AgentChatMessage, type ChatApiResponse } from "@/lib/api";

const ICON_LABEL: Record<string, string> = {
  general: "Auto",
};

export function AgentChat() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState<string>("general");
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api<Agent[]>("/agents").then(setAgents).catch(() => undefined);
  }, []);
  useEffect(() => {
    logEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;
    setError("");
    setDraft("");
    setBusy(true);
    setMessages((current) => [...current, { role: "user", content: message, agent: selected }]);
    try {
      const response = await api<ChatApiResponse>("/chat", {
        method: "POST",
        body: JSON.stringify({ message, agent: selected === "general" ? null : selected }),
      });
      setMessages((current) => [
        ...current,
        { role: "assistant", content: response.response, agent: response.agent, plan: response.plan },
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The agent could not respond.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="agent-panel" aria-labelledby="agent-panel-title">
      <div className="capability-heading">
        <span id="agent-panel-title">Specialist agents</span>
        <b>{String(agents.length).padStart(2, "0")}</b>
      </div>
      <div className="agent-pills" role="tablist" aria-label="Choose an agent">
        <button
          type="button"
          role="tab"
          aria-selected={selected === "general"}
          className="agent-pill"
          onClick={() => setSelected("general")}
        >
          Auto
        </button>
        {agents
          .filter((agent) => agent.id !== "general")
          .map((agent) => (
            <button
              key={agent.id}
              type="button"
              role="tab"
              aria-selected={selected === agent.id}
              className="agent-pill"
              disabled={agent.desktop_only}
              title={agent.desktop_only ? `${agent.name} requires the desktop app` : agent.description}
              onClick={() => setSelected(agent.id)}
            >
              {ICON_LABEL[agent.id] ?? agent.name}
              {agent.desktop_only && <i>desktop only</i>}
            </button>
          ))}
      </div>

      <div className="agent-message-stream" aria-live="polite">
        {messages.length === 0 ? (
          <p className="agent-empty">Ask a specialist agent — or leave it on Auto and JARVIS will route it for you.</p>
        ) : (
          messages.map((message, index) => (
            <article key={index} className={`agent-message agent-message-${message.role}`}>
              <div>
                <span>{message.role === "assistant" ? message.agent.toUpperCase() : "YOU"}</span>
              </div>
              <p>{message.content}</p>
              {message.plan && message.plan.length > 0 && (
                <ol className="agent-plan">
                  {message.plan.map((step) => (
                    <li key={step.step}>
                      <ListChecks size={12} />
                      <span>
                        <b>{step.tool}</b> — {step.description}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </article>
          ))
        )}
        <div ref={logEnd} />
      </div>

      <form className="agent-composer" onSubmit={submit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={`Ask the ${selected === "general" ? "assistant" : agents.find((agent) => agent.id === selected)?.name ?? "agent"}...`}
          aria-label="Message an agent"
          rows={2}
        />
        <Button type="submit" size="icon" aria-label="Send to agent" disabled={!draft.trim() || busy}>
          <ArrowUp size={16} />
        </Button>
      </form>
      {error && <p className="console-error" role="alert">{error}</p>}
    </section>
  );
}
