"use client";

import React, { useState, useEffect } from "react";
import { X, CheckCircle2, Clock, AlertTriangle, Play, Sparkles, Database, Plus, Search, Eye, EyeOff, Loader2, CheckCheck, ExternalLink, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

// ──────────────────────────────────────────────────────────────────────────────
// Provider Configuration Store (persisted to localStorage)
// ──────────────────────────────────────────────────────────────────────────────
const STORAGE_KEY = "jarvis_llm_providers";

export type ProviderStatus = "connected" | "not_linked" | "testing" | "error" | "no_models";

export interface ProviderConfig {
  name: string;
  apiKey: string;
  baseUrl?: string;          // for Ollama: http://localhost:11434
  status: ProviderStatus;
  model?: string;
  errorMsg?: string;
}

const DEFAULT_PROVIDERS: ProviderConfig[] = [
  { name: "Claude",      apiKey: "", status: "not_linked", model: "claude-3-5-sonnet-20241022" },
  { name: "OpenAI",      apiKey: "", status: "not_linked", model: "gpt-4o" },
  { name: "Gemini",      apiKey: "", status: "not_linked", model: "gemini-2.0-flash" },
  { name: "Groq",        apiKey: "", status: "connected",  model: "llama-3.3-70b-versatile" },
  { name: "OpenRouter",  apiKey: "", status: "connected",  model: "auto" },
  { name: "Ollama",      apiKey: "", baseUrl: "http://localhost:11434", status: "no_models" },
  { name: "Claude Code", apiKey: "", status: "connected",  model: "claude-3-5-sonnet-20241022" },
  { name: "Cursor",      apiKey: "", status: "connected",  model: "cursor-fast" },
  { name: "Copilot",     apiKey: "", status: "connected",  model: "gpt-4o" },
];

export function loadProviders(): ProviderConfig[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const saved: ProviderConfig[] = JSON.parse(raw);
      // Merge with defaults so new providers are always present
      return DEFAULT_PROVIDERS.map((def) => {
        const found = saved.find((s) => s.name === def.name);
        return found ? { ...def, ...found } : def;
      });
    }
  } catch (_) {}
  return DEFAULT_PROVIDERS;
}

export function saveProviders(providers: ProviderConfig[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(providers)); } catch (_) {}
}

// Quick connection testers
async function testProvider(p: ProviderConfig): Promise<{ ok: boolean; msg: string }> {
  try {
    if (p.name === "Claude") {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": p.apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({ model: p.model || "claude-3-haiku-20240307", max_tokens: 8, messages: [{ role: "user", content: "ping" }] }),
      });
      if (r.ok || r.status === 400) return { ok: true, msg: "Authenticated" };
      const err = await r.json().catch(() => ({}));
      return { ok: false, msg: err?.error?.message || `HTTP ${r.status}` };
    }

    if (p.name === "OpenAI") {
      const r = await fetch("https://api.openai.com/v1/models", {
        headers: { Authorization: `Bearer ${p.apiKey}` },
      });
      if (r.ok) return { ok: true, msg: "Authenticated" };
      const err = await r.json().catch(() => ({}));
      return { ok: false, msg: err?.error?.message || `HTTP ${r.status}` };
    }

    if (p.name === "Gemini") {
      const r = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models?key=${p.apiKey}`
      );
      if (r.ok) return { ok: true, msg: "Authenticated" };
      const err = await r.json().catch(() => ({}));
      return { ok: false, msg: err?.error?.message || `HTTP ${r.status}` };
    }

    if (p.name === "Groq") {
      const r = await fetch("https://api.groq.com/openai/v1/models", {
        headers: { Authorization: `Bearer ${p.apiKey}` },
      });
      if (r.ok) return { ok: true, msg: "Authenticated" };
      return { ok: false, msg: `HTTP ${r.status}` };
    }

    if (p.name === "OpenRouter") {
      const r = await fetch("https://openrouter.ai/api/v1/models", {
        headers: { Authorization: `Bearer ${p.apiKey}` },
      });
      if (r.ok) return { ok: true, msg: "Authenticated" };
      return { ok: false, msg: `HTTP ${r.status}` };
    }

    if (p.name === "Ollama") {
      const base = p.baseUrl || "http://localhost:11434";
      const r = await fetch(`${base}/api/tags`, { signal: AbortSignal.timeout(4000) });
      if (r.ok) {
        const data = await r.json();
        const count = data?.models?.length ?? 0;
        return { ok: count > 0, msg: count > 0 ? `${count} models found` : "No models pulled yet" };
      }
      return { ok: false, msg: "Ollama not reachable" };
    }

    return { ok: true, msg: "No test available" };
  } catch (e: any) {
    return { ok: false, msg: e?.message || "Network error" };
  }
}

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

export function HudModal({ isOpen, onClose, title, children }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border border-cyan-500/50 bg-[#071322]/95 shadow-[0_0_30px_rgba(0,229,255,0.25)] text-cyan-100 overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-cyan-500/20 bg-cyan-950/20">
          <div className="flex items-center gap-2.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_#00e5ff]" />
            <h3 className="text-base font-bold tracking-wider text-cyan-200 uppercase font-mono">{title}</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-cyan-400 hover:text-white hover:bg-cyan-500/20 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 font-sans text-sm custom-scrollbar">
          {children}
        </div>
      </div>
    </div>
  );
}

export function NewTaskModal({
  isOpen,
  onClose,
  onSubmit,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (title: string, priority: string) => void;
}) {
  const [taskTitle, setTaskTitle] = useState("");
  const [priority, setPriority] = useState("medium");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    onSubmit(taskTitle, priority);
    setTaskTitle("");
    onClose();
  };

  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="Start New Task">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs uppercase tracking-wider text-cyan-400/80 mb-1.5 font-mono">
            Task Objective / Instruction
          </label>
          <textarea
            value={taskTitle}
            onChange={(e) => setTaskTitle(e.target.value)}
            rows={3}
            placeholder="e.g. Analyze server logs and summarize open ports..."
            className="w-full rounded-lg border border-cyan-500/30 bg-[#020b14] px-3.5 py-2.5 text-cyan-100 placeholder-cyan-600/60 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 text-sm"
            autoFocus
          />
        </div>

        <div className="flex items-center justify-between pt-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-cyan-400/70 font-mono">Priority:</span>
            {(["low", "medium", "urgent"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={`px-3 py-1 rounded text-xs uppercase font-mono transition border ${
                  priority === p
                    ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                    : "border-cyan-500/20 text-cyan-400/50 hover:border-cyan-500/40"
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 rounded text-xs font-mono border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/10 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!taskTitle.trim()}
              className="px-4 py-1.5 rounded text-xs font-mono font-semibold bg-cyan-500 text-[#020b14] hover:bg-cyan-400 transition shadow-[0_0_12px_rgba(0,229,255,0.4)] disabled:opacity-50"
            >
              Queue Task
            </button>
          </div>
        </div>
      </form>
    </HudModal>
  );
}

export function CalendarModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const events = [
    { time: "09:30 am", title: "Daily Standup", status: "Done", duration: "30m" },
    { time: "12:00 pm", title: "Finalize HUD panel spacing", status: "In 42 min", duration: "45m" },
    { time: "02:00 pm", title: "Deep-work block: Voice pipeline", status: "In 2h 42m", duration: "2h" },
    { time: "04:30 pm", title: "Design Review — Command Center V1", status: "In 5h 12m", duration: "1h" },
    { time: "06:00 pm", title: "AI Model Alignment Check", status: "Upcoming", duration: "30m" },
  ];

  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="Mission Timeline & Schedule">
      <div className="space-y-3">
        {events.map((ev, i) => (
          <div
            key={i}
            className="flex items-center justify-between p-3 rounded-lg border border-cyan-500/20 bg-[#040e1a]/80"
          >
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-cyan-300 font-semibold">{ev.time}</span>
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
              <span className="text-cyan-100 font-medium">{ev.title}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-cyan-400/60">{ev.duration}</span>
              <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                ev.status === "Done"
                  ? "border-emerald-500/40 text-emerald-300 bg-emerald-950/30"
                  : "border-cyan-500/40 text-cyan-300 bg-cyan-950/30"
              }`}>
                {ev.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </HudModal>
  );
}

export function IntelligenceModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const items = [
    { title: "Design review with the product team...", tag: "INFO", cat: "Meeting", color: "text-cyan-400 border-cyan-500/30" },
    { title: "2 tasks are overdue - 'Polish voice...'", tag: "WARN", cat: "Overdue", color: "text-amber-400 border-amber-500/30" },
    { title: "3 pull requests are awaiting your review...", tag: "TIP", cat: "Github", color: "text-blue-400 border-blue-500/30" },
    { title: "Your deep-work block is 2-4 PM. Notifications muted.", tag: "TIP", cat: "Focus", color: "text-blue-400 border-blue-500/30" },
    { title: "CPU usage at 15% System load nominal", tag: "LIVE", cat: "System", color: "text-emerald-400 border-emerald-500/30" },
    { title: "2 tasks overdue — Review the board and reschedule...", tag: "ALERT", cat: "Tasks", color: "text-rose-400 border-rose-500/30" },
    { title: "Security boundary check passed: All 14 endpoints isolated", tag: "SEC", cat: "Audit", color: "text-teal-400 border-teal-500/30" },
    { title: "Gemini Live session ready: Low-latency audio pipeline active", tag: "LIVE", cat: "Voice", color: "text-cyan-300 border-cyan-400/30" },
  ];

  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="Live Intelligence Feed">
      <div className="space-y-2.5">
        {items.map((item, i) => (
          <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-cyan-500/20 bg-[#040e1a]/70">
            <span className="text-cyan-100 text-sm">{item.title}</span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase tracking-wider ${item.color}`}>
              {item.tag} / {item.cat}
            </span>
          </div>
        ))}
      </div>
    </HudModal>
  );
}

export function ManageProvidersModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [editKey, setEditKey] = useState<Record<string, string>>({});
  const [editUrl, setEditUrl] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  // Load from localStorage on open
  useEffect(() => {
    if (isOpen) {
      const loaded = loadProviders();
      setProviders(loaded);
      const keys: Record<string, string> = {};
      const urls: Record<string, string> = {};
      loaded.forEach((p) => {
        keys[p.name] = p.apiKey || "";
        urls[p.name] = p.baseUrl || "";
      });
      setEditKey(keys);
      setEditUrl(urls);
    }
  }, [isOpen]);

  const providerMeta: Record<string, { color: string; keyLabel: string; keyPlaceholder: string; helpUrl: string; hasUrl?: boolean; isLocal?: boolean }> = {
    Claude:      { color: "border-orange-500/40 bg-orange-950/20", keyLabel: "Anthropic API Key", keyPlaceholder: "sk-ant-...",               helpUrl: "https://console.anthropic.com/settings/keys" },
    OpenAI:      { color: "border-emerald-500/40 bg-emerald-950/20", keyLabel: "OpenAI API Key",   keyPlaceholder: "sk-proj-...",               helpUrl: "https://platform.openai.com/api-keys" },
    Gemini:      { color: "border-blue-500/40 bg-blue-950/20", keyLabel: "Google AI API Key",     keyPlaceholder: "AIzaSy...",                  helpUrl: "https://aistudio.google.com/app/apikey" },
    Groq:        { color: "border-amber-500/40 bg-amber-950/20", keyLabel: "Groq API Key",        keyPlaceholder: "gsk_...",                    helpUrl: "https://console.groq.com/keys" },
    OpenRouter:  { color: "border-purple-500/40 bg-purple-950/20", keyLabel: "OpenRouter API Key", keyPlaceholder: "sk-or-v1-...",              helpUrl: "https://openrouter.ai/keys" },
    Ollama:      { color: "border-teal-500/40 bg-teal-950/20", keyLabel: "No API key needed",     keyPlaceholder: "(leave blank)",              helpUrl: "https://ollama.com/download", hasUrl: true, isLocal: true },
    "Claude Code": { color: "border-orange-400/30 bg-orange-950/10", keyLabel: "Anthropic API Key", keyPlaceholder: "sk-ant-...",              helpUrl: "https://console.anthropic.com/settings/keys" },
    Cursor:      { color: "border-cyan-500/40 bg-cyan-950/20", keyLabel: "Cursor API Key",        keyPlaceholder: "(managed by Cursor IDE)",   helpUrl: "https://cursor.sh" },
    Copilot:     { color: "border-cyan-400/30 bg-cyan-950/10", keyLabel: "GitHub Token",          keyPlaceholder: "ghp_...",                   helpUrl: "https://github.com/settings/tokens" },
  };

  const test = async (name: string) => {
    const idx = providers.findIndex((p) => p.name === name);
    if (idx < 0) return;
    const updated = [...providers];
    updated[idx] = { ...updated[idx], status: "testing", errorMsg: undefined };
    setProviders(updated);

    const result = await testProvider({
      ...updated[idx],
      apiKey: editKey[name] || "",
      baseUrl: editUrl[name] || updated[idx].baseUrl,
    });

    updated[idx] = {
      ...updated[idx],
      apiKey: editKey[name] || "",
      baseUrl: editUrl[name] || updated[idx].baseUrl,
      status: result.ok ? "connected" : "error",
      errorMsg: result.ok ? undefined : result.msg,
    };
    setProviders(updated);
    saveProviders(updated);
    setSaved((s) => ({ ...s, [name]: true }));
    setTimeout(() => setSaved((s) => ({ ...s, [name]: false })), 2500);
  };

  const disconnect = (name: string) => {
    const idx = providers.findIndex((p) => p.name === name);
    if (idx < 0) return;
    const updated = [...providers];
    updated[idx] = { ...updated[idx], apiKey: "", status: "not_linked", errorMsg: undefined };
    setProviders(updated);
    setEditKey((k) => ({ ...k, [name]: "" }));
    saveProviders(updated);
  };

  const statusColors: Record<ProviderStatus, string> = {
    connected:  "text-emerald-400 bg-emerald-950/50 border-emerald-500/40",
    not_linked: "text-cyan-400/60 bg-[#030d1a] border-cyan-500/15",
    testing:    "text-amber-300 bg-amber-950/30 border-amber-500/30",
    error:      "text-rose-400 bg-rose-950/30 border-rose-500/30",
    no_models:  "text-cyan-400/50 bg-[#030d1a] border-cyan-500/15",
  };

  const statusDot: Record<ProviderStatus, string> = {
    connected:  "bg-emerald-400 shadow-[0_0_6px_#10b981]",
    not_linked: "bg-cyan-800",
    testing:    "bg-amber-400 animate-pulse",
    error:      "bg-rose-400 shadow-[0_0_6px_#f43f5e]",
    no_models:  "bg-cyan-700",
  };

  const statusLabel: Record<ProviderStatus, string> = {
    connected:  "Connected",
    not_linked: "Not Linked",
    testing:    "Testing...",
    error:      "Error",
    no_models:  "No Models",
  };

  const linkable = ["Claude", "OpenAI", "Gemini", "Ollama", "Groq", "OpenRouter"];

  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="LLM Provider Matrix — Link / Manage">
      <div className="space-y-3">

        {/* ── How to link banner ── */}
        <div className="flex items-start gap-3 p-3 rounded-lg border border-cyan-500/20 bg-[#030f1f]">
          <AlertCircle className="w-4 h-4 text-cyan-400 flex-shrink-0 mt-0.5" />
          <p className="text-[11px] text-cyan-300/80 leading-relaxed">
            Click any provider card to expand it, paste your API key, then hit{" "}
            <strong className="text-cyan-200">Test & Connect</strong>. Keys are stored only in your browser's localStorage —
            they are never sent to any JARVIS server.
          </p>
        </div>

        {/* ── Provider Grid ── */}
        <div className="space-y-2">
          {providers.map((p) => {
            const meta = providerMeta[p.name] ?? { color: "border-cyan-500/20 bg-[#030d1a]", keyLabel: "API Key", keyPlaceholder: "...", helpUrl: "#" };
            const isExpanded = selectedProvider === p.name;
            const isLinkable = linkable.includes(p.name);

            return (
              <div
                key={p.name}
                className={`rounded-lg border transition-all ${isExpanded ? meta.color : statusColors[p.status]} overflow-hidden`}
              >
                {/* Card Header Row */}
                <div
                  className="flex items-center justify-between px-3.5 py-2.5 cursor-pointer"
                  onClick={() => setSelectedProvider(isExpanded ? null : p.name)}
                >
                  <div className="flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot[p.status]}`} />
                    <div>
                      <span className="font-mono font-bold text-cyan-100 text-sm">{p.name}</span>
                      {p.status === "connected" && (
                        <span className="ml-2 text-[10px] font-mono text-emerald-400">● Connected</span>
                      )}
                      {p.status === "error" && (
                        <span className="ml-2 text-[10px] font-mono text-rose-400">✖ {p.errorMsg?.slice(0, 40)}</span>
                      )}
                      {p.status === "testing" && (
                        <span className="ml-2 text-[10px] font-mono text-amber-300">⟳ Testing...</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase tracking-wider ${statusColors[p.status]}`}>
                      {statusLabel[p.status]}
                    </span>
                    {isLinkable && (
                      isExpanded ? <ChevronUp size={14} className="text-cyan-400/60" /> : <ChevronDown size={14} className="text-cyan-400/60" />
                    )}
                  </div>
                </div>

                {/* Expanded: API key form */}
                {isExpanded && (
                  <div className="px-3.5 pb-4 pt-0 border-t border-cyan-500/15 space-y-3">

                    {/* Key/URL input */}
                    <div className="space-y-2 pt-3">
                      {/* API Key field */}
                      {!meta.isLocal && (
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <label className="text-[11px] font-mono text-cyan-400/80 uppercase tracking-wider">
                              {meta.keyLabel}
                            </label>
                            <a
                              href={meta.helpUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="flex items-center gap-1 text-[10px] font-mono text-cyan-400 hover:text-cyan-200 transition"
                            >
                              Get API Key <ExternalLink size={10} />
                            </a>
                          </div>
                          <div className="relative">
                            <input
                              type={showKey[p.name] ? "text" : "password"}
                              value={editKey[p.name] ?? ""}
                              onChange={(e) => setEditKey((k) => ({ ...k, [p.name]: e.target.value }))}
                              placeholder={meta.keyPlaceholder}
                              className="w-full pr-9 pl-3 py-2 rounded border border-cyan-500/25 bg-[#020b14] text-cyan-100 placeholder-cyan-600/40 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 font-mono text-xs"
                              autoComplete="off"
                              spellCheck={false}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); setShowKey((s) => ({ ...s, [p.name]: !s[p.name] })); }}
                              className="absolute right-2.5 top-2 text-cyan-400/60 hover:text-cyan-200 transition"
                            >
                              {showKey[p.name] ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Ollama base URL */}
                      {meta.hasUrl && (
                        <div>
                          <label className="text-[11px] font-mono text-cyan-400/80 uppercase tracking-wider block mb-1">
                            Ollama Base URL
                          </label>
                          <input
                            type="text"
                            value={editUrl[p.name] ?? "http://localhost:11434"}
                            onChange={(e) => setEditUrl((u) => ({ ...u, [p.name]: e.target.value }))}
                            placeholder="http://localhost:11434"
                            className="w-full px-3 py-2 rounded border border-cyan-500/25 bg-[#020b14] text-cyan-100 placeholder-cyan-600/40 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 font-mono text-xs"
                            onClick={(e) => e.stopPropagation()}
                          />
                          <p className="text-[10px] text-cyan-400/50 mt-1 font-mono">
                            Make sure Ollama is running locally.{" "}
                            <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-200">
                              Download Ollama ↗
                            </a>
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Model hint */}
                    {p.model && (
                      <p className="text-[10px] font-mono text-cyan-400/50">
                        Default model: <span className="text-cyan-300/80">{p.model}</span>
                      </p>
                    )}

                    {/* Action buttons */}
                    <div className="flex items-center justify-between gap-2 pt-1">
                      {p.status === "connected" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); disconnect(p.name); }}
                          className="px-3 py-1.5 rounded text-[11px] font-mono border border-rose-500/30 text-rose-400 hover:bg-rose-950/50 transition"
                        >
                          Disconnect
                        </button>
                      )}
                      <div className="flex-1" />
                      <button
                        onClick={(e) => { e.stopPropagation(); test(p.name); }}
                        disabled={p.status === "testing"}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-mono font-semibold bg-cyan-500 text-[#020b14] hover:bg-cyan-400 transition shadow-[0_0_10px_rgba(0,229,255,0.4)] disabled:opacity-60"
                      >
                        {p.status === "testing" ? (
                          <><Loader2 size={12} className="animate-spin" /> Testing...</>
                        ) : saved[p.name] ? (
                          <><CheckCheck size={12} /> Saved!</>
                        ) : (
                          <><CheckCircle2 size={12} /> Test & Connect</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Quick stats */}
        <div className="flex items-center justify-between text-[11px] font-mono text-cyan-400/60 pt-1 border-t border-cyan-500/10">
          <span>{providers.filter((p) => p.status === "connected").length} of {providers.length} providers connected</span>
          <a href="https://aistudio.google.com" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:text-cyan-200 flex items-center gap-1">
            Get free API keys <ExternalLink size={11} />
          </a>
        </div>
      </div>
    </HudModal>
  );
}


export function ExecutiveBriefingModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="Executive Daily Briefing">
      <div className="space-y-4 text-cyan-100">
        <div className="p-4 rounded-lg border border-cyan-500/30 bg-cyan-950/20 flex items-start gap-3">
          <Sparkles className="w-5 h-5 text-cyan-300 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="font-mono text-cyan-200 font-bold mb-1">Good morning, Commander.</h4>
            <p className="text-cyan-300/80 text-xs leading-relaxed">
              All primary subsystems are operating at optimal parameters. You have 4 timeline milestones today,
              with 2 overdue tasks requiring reschedule. System load is nominal at 15% CPU and 54% RAM.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 font-mono text-xs">
          <div className="p-3 rounded border border-cyan-500/20 bg-[#030a14]">
            <span className="text-cyan-400/70 block mb-1">SCHEDULED TODAY</span>
            <span className="text-xl font-bold text-cyan-200">4 Events</span>
          </div>
          <div className="p-3 rounded border border-cyan-500/20 bg-[#030a14]">
            <span className="text-cyan-400/70 block mb-1">STORED MEMORIES</span>
            <span className="text-xl font-bold text-cyan-200">3,380 Entries</span>
          </div>
        </div>

        <div className="pt-2 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded font-mono text-xs font-semibold bg-cyan-500 text-[#020b14] hover:bg-cyan-400 transition shadow-[0_0_12px_rgba(0,229,255,0.4)]"
          >
            Acknowledge Briefing
          </button>
        </div>
      </div>
    </HudModal>
  );
}

export function CommandPaletteModal({
  isOpen,
  onClose,
  onSelectAction,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSelectAction: (action: string) => void;
}) {
  const [query, setQuery] = useState("");

  const commands = [
    { label: "Start New Task", action: "new_task", icon: Plus, cat: "Task" },
    { label: "Open Calendar Schedule", action: "open_calendar", icon: Clock, cat: "Schedule" },
    { label: "Start Voice Chat", action: "voice_chat", icon: Sparkles, cat: "Voice" },
    { label: "Run Automated Workflow", action: "run_workflow", icon: Play, cat: "Automation" },
    { label: "View Memory Map", action: "memory_map", icon: Database, cat: "Memory" },
    { label: "Manage LLM Providers", action: "manage_providers", icon: Sparkles, cat: "AI Core" },
    { label: "Trigger Executive Briefing", action: "executive_briefing", icon: Sparkles, cat: "Briefing" },
  ];

  const filtered = commands.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <HudModal isOpen={isOpen} onClose={onClose} title="Command Palette">
      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3.5 top-3 w-4 h-4 text-cyan-400/60" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search action..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-cyan-500/30 bg-[#020b14] text-cyan-100 placeholder-cyan-600/60 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 font-mono text-sm"
            autoFocus
          />
        </div>

        <div className="divide-y divide-cyan-500/10 max-h-64 overflow-y-auto custom-scrollbar">
          {filtered.map((cmd) => {
            const Icon = cmd.icon;
            return (
              <button
                key={cmd.action}
                onClick={() => {
                  onSelectAction(cmd.action);
                  onClose();
                }}
                className="w-full flex items-center justify-between p-2.5 rounded-lg hover:bg-cyan-500/10 text-left transition group"
              >
                <div className="flex items-center gap-2.5">
                  <Icon className="w-4 h-4 text-cyan-400 group-hover:text-cyan-200" />
                  <span className="text-cyan-200 text-sm font-medium">{cmd.label}</span>
                </div>
                <span className="text-[10px] font-mono text-cyan-400/50 uppercase tracking-wider">{cmd.cat}</span>
              </button>
            );
          })}
        </div>
      </div>
    </HudModal>
  );
}
