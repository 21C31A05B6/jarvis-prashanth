"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  Brain,
  Calendar,
  Check,
  CheckSquare,
  Clock,
  Code2,
  Cpu,
  Database,
  ExternalLink,
  Flame,
  Globe,
  Grid,
  Layers,
  LayoutDashboard,
  MessageSquare,
  Mic,
  MicOff,
  Minimize2,
  Maximize2,
  Moon,
  Network,
  Play,
  Plus,
  Radio,
  Search,
  Settings,
  Share2,
  Shield,
  ShieldCheck,
  Sparkles,
  Terminal,
  Volume2,
  Wifi,
  Wrench,
  X,
} from "lucide-react";
import { useJarvisSocket } from "@/hooks/use-jarvis-socket";
import { type User } from "@/lib/api";
import { HologramSphere } from "./hologram-sphere";
import { MemoryConstellation } from "./memory-constellation";
import { RadialGauge } from "./radial-gauge";
import {
  NewTaskModal,
  CalendarModal,
  IntelligenceModal,
  ManageProvidersModal,
  ExecutiveBriefingModal,
  CommandPaletteModal,
} from "./hud-modals";

export function JarvisConsole({
  user,
  onSignOut,
}: {
  user?: User;
  onSignOut?: () => void;
}) {
  const live = useJarvisSocket();

  // Active navigation tab
  const [activeTab, setActiveTab] = useState("Command Center");
  const [focusMode, setFocusMode] = useState(false);

  // Time and Date state
  const [currentTime, setCurrentTime] = useState("");
  const [currentDate, setCurrentDate] = useState("");

  // Modal states
  const [showNewTask, setShowNewTask] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [showIntelligence, setShowIntelligence] = useState(false);
  const [showProviders, setShowProviders] = useState(false);
  const [showBriefing, setShowBriefing] = useState(false);
  const [showPalette, setShowPalette] = useState(false);

  // Voice recognition fallback
  const [isListeningLocal, setIsListeningLocal] = useState(false);
  const [spokenTranscript, setSpokenTranscript] = useState("");

  // System Metrics
  const [metrics, setMetrics] = useState({ cpu: 15, ram: 54, disk: 40 });

  // Clock tick
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      // "Monday, 15 June 2026"
      const dateStr = now.toLocaleDateString("en-US", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });
      // "11:18:21 am"
      const timeStr = now.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
      }).toLowerCase();

      setCurrentDate(dateStr);
      setCurrentTime(timeStr);
    };

    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcut Ctrl+K / Cmd+K for Command Palette
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowPalette((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Toggle Voice Input
  const toggleVoice = () => {
    if (live.micActive) {
      live.stopMic();
      setIsListeningLocal(false);
    } else {
      live.startMic();
      // Fallback Web Speech API for local browser transcription
      if (typeof window !== "undefined" && ("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
        try {
          const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
          const recognition = new SpeechRecognition();
          recognition.continuous = false;
          recognition.interimResults = true;
          recognition.onresult = (event: any) => {
            const current = event.resultIndex;
            const text = event.results[current][0].transcript;
            setSpokenTranscript(text);
          };
          recognition.onend = () => {
            setIsListeningLocal(false);
          };
          recognition.start();
          setIsListeningLocal(true);
        } catch (err) {
          console.warn("Local speech recognition unavailable:", err);
        }
      }
    }
  };

  // Executive Briefing Audio Synthesizer
  const handleExecutiveBriefing = () => {
    setShowBriefing(true);
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(
        "Good morning, Commander. All systems are operational at optimal parameters. You have four scheduled milestones today. System load is nominal."
      );
      utterance.pitch = 0.95;
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
    }
  };

  const navItems = [
    { label: "Command Center", icon: LayoutDashboard },
    { label: "AI Core", icon: Cpu },
    { label: "Agents", icon: Bot },
    { label: "Tasks", icon: CheckSquare, badge: 3 },
    { label: "Calendar", icon: Calendar },
    { label: "Memory", icon: Database },
    { label: "Conversations", icon: MessageSquare, badge: 12 },
    { label: "Knowledge Base", icon: Brain },
    { label: "Tools & Skills", icon: Wrench, badge: 18 },
    { label: "Workflows", icon: Share2 },
  ];

  return (
    <div className="hud-root min-h-screen bg-[#020b14] text-[#c9e6ff] flex flex-col font-sans select-none overflow-x-hidden">
      {/* ─────────────────────────────────────────────────────────────
          1. TOP BAR HEADER
      ────────────────────────────────────────────────────────────── */}
      <header className="h-14 border-b border-[#0f3254]/80 bg-[#031120]/90 backdrop-blur-md px-4 flex items-center justify-between z-30 flex-shrink-0">
        {/* Left: JARVIS Logo + Subtitle + System Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            {/* Concentric Glowing Reactor Glyph */}
            <div className="relative w-7 h-7 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border border-cyan-400/60 animate-spin-slow shadow-[0_0_10px_#00e5ff]" />
              <div className="w-3.5 h-3.5 rounded-full border border-cyan-300 bg-cyan-950 flex items-center justify-center">
                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
              </div>
            </div>

            <div className="flex flex-col">
              <span className="text-base font-extrabold tracking-[0.18em] text-white leading-none font-mono">
                JARVIS
              </span>
              <span className="text-[9px] tracking-[0.25em] text-cyan-400/80 font-mono uppercase mt-0.5">
                COMMAND CENTER
              </span>
            </div>
          </div>

          {/* SYSTEM STATUS Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-cyan-500/30 bg-[#06182c]/80 text-[11px] font-mono">
            <span className="text-cyan-300/70 text-[10px] tracking-wider uppercase font-semibold">SYSTEM STATUS</span>
            <span className="flex items-center gap-1 text-emerald-400 font-bold tracking-wider text-[10px] uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981]" />
              OPTIMAL
            </span>
          </div>
        </div>

        {/* Center: Live Date & Glowing Monospace Digital Clock */}
        <div className="flex flex-col items-center justify-center">
          <span className="text-[11px] font-medium tracking-wide text-cyan-300/70 font-sans">
            {currentDate || "Monday, 15 June 2026"}
          </span>
          <span
            className="text-base md:text-lg font-bold tracking-wider text-cyan-300 font-mono leading-tight"
            style={{
              textShadow: "0 0 10px rgba(0, 229, 255, 0.75), 0 0 20px rgba(0, 160, 255, 0.4)",
            }}
          >
            {currentTime || "11:18:21 am"}
          </span>
        </div>

        {/* Right: Search + Quick Tools + Operator Badge */}
        <div className="flex items-center gap-3">
          {/* Search Bar with Ctrl+K */}
          <button
            onClick={() => setShowPalette(true)}
            className="hidden md:flex items-center justify-between gap-3 px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-[#05162a]/90 text-cyan-400/70 hover:border-cyan-400/50 hover:text-cyan-200 transition text-xs font-mono w-44"
          >
            <span className="flex items-center gap-1.5">
              <Search size={13} className="text-cyan-400/70" />
              Search...
            </span>
            <kbd className="px-1.5 py-0.5 rounded bg-[#09223c] border border-cyan-500/30 text-[9px] text-cyan-300">
              Ctrl+K
            </kbd>
          </button>

          {/* Action Icons: Grid, Bell, Settings */}
          <div className="flex items-center gap-1.5 text-cyan-400/80">
            <button
              onClick={() => setShowPalette(true)}
              className="p-1.5 rounded-lg hover:bg-cyan-500/15 hover:text-cyan-200 transition"
              title="Apps"
            >
              <Grid size={16} />
            </button>
            <button
              onClick={() => setShowIntelligence(true)}
              className="p-1.5 rounded-lg hover:bg-cyan-500/15 hover:text-cyan-200 transition relative"
              title="Notifications"
            >
              <Bell size={16} />
              <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
            </button>
            <button
              onClick={() => setShowProviders(true)}
              className="p-1.5 rounded-lg hover:bg-cyan-500/15 hover:text-cyan-200 transition"
              title="Settings"
            >
              <Settings size={16} />
            </button>
          </div>

          {/* Operator Commander Profile Pill */}
          <div className="flex items-center gap-2 pl-2 border-l border-cyan-500/20">
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full border border-cyan-500/30 bg-[#06192e] text-xs font-mono">
              <div className="w-5 h-5 rounded-full bg-cyan-900 border border-cyan-400 flex items-center justify-center text-[10px] text-cyan-200 font-bold">
                O
              </div>
              <div className="flex flex-col text-left">
                <span className="text-[11px] font-semibold text-cyan-200 leading-tight">Operator</span>
                <span className="text-[9px] text-cyan-400/60 leading-none">Commander</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ─────────────────────────────────────────────────────────────
          MAIN BODY LAYOUT: SIDEBAR + DASHBOARD GRID
      ────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT NAVIGATION SIDEBAR */}
        {!focusMode && (
          <aside className="w-56 border-r border-[#0f3254]/80 bg-[#020d18]/90 flex flex-col justify-between p-3 flex-shrink-0 z-20">
            {/* Navigation links */}
            <nav className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.label;

                return (
                  <button
                    key={item.label}
                    onClick={() => {
                      setActiveTab(item.label);
                      if (item.label === "Tasks") setShowNewTask(true);
                      if (item.label === "Calendar") setShowCalendar(true);
                      if (item.label === "Knowledge Base" || item.label === "Memory") setShowIntelligence(true);
                    }}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium font-mono transition group ${
                      isActive
                        ? "border border-cyan-400/60 bg-gradient-to-r from-cyan-500/20 to-cyan-500/5 text-cyan-200 shadow-[0_0_12px_rgba(0,229,255,0.2)]"
                        : "border border-transparent text-cyan-400/70 hover:text-cyan-200 hover:bg-cyan-500/10 hover:border-cyan-500/20"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <Icon
                        size={15}
                        className={isActive ? "text-cyan-300 drop-shadow-[0_0_6px_#00e5ff]" : "text-cyan-400/70"}
                      />
                      <span>{item.label}</span>
                    </div>
                    {item.badge !== undefined && (
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full border border-cyan-500/30 bg-[#051b32] text-cyan-300">
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </nav>

            {/* VOICE STATUS Panel at bottom of sidebar */}
            <div className="pt-3 border-t border-cyan-500/20 flex flex-col items-center">
              <div className="w-full flex items-center justify-between text-[11px] font-mono text-cyan-400/80 mb-2 px-1">
                <span className="tracking-wider uppercase font-semibold">VOICE STATUS</span>
                <span className="text-cyan-400/50">&gt;</span>
              </div>

              {/* Dynamic Audio Equalizer Bars */}
              <div className="flex items-center gap-1 h-6 my-1">
                {[4, 8, 14, 20, 15, 10, 6, 12, 18, 11, 5].map((h, i) => (
                  <div
                    key={i}
                    className="w-1 bg-cyan-400/80 rounded-full animate-pulse shadow-[0_0_6px_#00e5ff]"
                    style={{
                      height: `${h}px`,
                      animationDelay: `${i * 0.12}s`,
                      animationDuration: "0.8s",
                    }}
                  />
                ))}
              </div>

              {/* Status caption */}
              <span className="text-[11px] font-mono text-cyan-300/80 mt-1 mb-2">
                {live.micActive || isListeningLocal ? "Listening..." : "Standby"}
              </span>

              {/* Glowing Concentric Circular Mic Button: Tap to Speak */}
              <button
                onClick={toggleVoice}
                className="relative group p-3 rounded-full flex flex-col items-center justify-center transition"
              >
                {/* Ripple rings */}
                <div className="absolute inset-0 rounded-full border border-cyan-400/40 animate-ping opacity-30" />
                <div className="w-12 h-12 rounded-full border-2 border-cyan-400 bg-gradient-to-b from-[#062c4a] to-[#021324] shadow-[0_0_18px_rgba(0,229,255,0.6)] flex items-center justify-center group-hover:scale-105 transition">
                  {live.micActive || isListeningLocal ? (
                    <Mic className="text-cyan-200 drop-shadow-[0_0_8px_#00e5ff]" size={20} />
                  ) : (
                    <MicOff className="text-cyan-400/60" size={18} />
                  )}
                </div>
              </button>
              <span className="text-[10px] font-mono text-cyan-400/60 mt-1">Tap to Speak</span>

              {/* Focus Mode Button */}
              <button
                onClick={() => setFocusMode(!focusMode)}
                className="mt-3 w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg border border-cyan-500/25 bg-[#041628] text-cyan-300 text-xs font-mono hover:border-cyan-400 hover:bg-cyan-500/10 transition shadow-[0_0_10px_rgba(0,229,255,0.15)]"
              >
                <Sparkles size={12} className="text-cyan-300" />
                <span>Focus Mode</span>
              </button>
            </div>
          </aside>
        )}

        {/* ─────────────────────────────────────────────────────────────
            MAIN DASHBOARD CONTENT (HUD CARDS GRID)
        ────────────────────────────────────────────────────────────── */}
        <main className="flex-1 p-2.5 overflow-y-auto xl:overflow-hidden space-y-2.5 custom-scrollbar">
          {/* ── TOP ROW: AI Core Overview | 3D Holographic Globe | Live Intelligence Feed ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-2.5">
            {/* Top Left: AI CORE OVERVIEW */}
            <section className="lg:col-span-3 hud-card p-2.5 flex flex-col justify-between">
              <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono mb-2">
                AI CORE OVERVIEW
              </h2>

              <div className="space-y-2">
                {[
                  { title: "AI Core", sub: "Active", icon: Cpu, color: "text-cyan-400", bg: "bg-cyan-950 border-cyan-500/40" },
                  { title: "Memory", sub: "3,380 Stored", icon: Database, color: "text-blue-400", bg: "bg-blue-950 border-blue-500/40" },
                  { title: "Voice", sub: "Online", icon: Mic, color: "text-teal-400", bg: "bg-teal-950 border-teal-500/40" },
                  { title: "Agents", sub: "2 Running", icon: Bot, color: "text-purple-400", bg: "bg-purple-950 border-purple-500/40" },
                  { title: "LLMs", sub: "4 Connected", icon: Brain, color: "text-amber-400", bg: "bg-amber-950 border-amber-500/40" },
                  { title: "System", sub: "Optimal", icon: Shield, color: "text-emerald-400", bg: "bg-emerald-950 border-emerald-500/40" },
                ].map((item, i) => {
                  const Icon = item.icon;
                  return (
                    <div key={i} className="flex items-center gap-2.5">
                      <div className={`w-6 h-6 rounded-full border flex items-center justify-center ${item.bg}`}>
                        <Icon size={13} className={item.color} />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-xs font-bold text-cyan-100 font-mono leading-none">{item.title}</span>
                        <span className={`text-[10px] font-mono leading-none mt-0.5 ${item.color}`}>{item.sub}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Center Hero: 3D Holographic AI Core Sphere */}
            <section className="lg:col-span-6 hud-card p-1.5 relative flex flex-col items-center justify-center min-h-[210px]">
              <HologramSphere width={420} height={205} />
            </section>

            {/* Top Right: LIVE INTELLIGENCE FEED */}
            <section className="lg:col-span-3 hud-card p-2.5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono">
                  LIVE INTELLIGENCE FEED
                </h2>
                <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_#10b981]" />
                  LIVE
                </span>
              </div>

              <div className="space-y-2 text-[11px] font-sans">
                {/* Item 1 */}
                <div className="flex items-start justify-between gap-1.5 pb-1 border-b border-cyan-500/10">
                  <span className="text-cyan-200 truncate max-w-[155px]">Design review with the product tea...</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-cyan-500/30 text-cyan-300 bg-cyan-950/40 uppercase">
                    INFO
                  </span>
                </div>

                {/* Item 2 */}
                <div className="flex items-start justify-between gap-1.5 pb-1 border-b border-cyan-500/10">
                  <span className="text-amber-200/90 truncate max-w-[155px]">2 tasks are overdue - "Polish voic...</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-300 bg-amber-950/40 uppercase">
                    WARN
                  </span>
                </div>

                {/* Item 3 */}
                <div className="flex items-start justify-between gap-1.5 pb-1 border-b border-cyan-500/10">
                  <span className="text-blue-200 truncate max-w-[155px]">3 pull requests are awaiting your revi...</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-blue-500/30 text-blue-300 bg-blue-950/40 uppercase">
                    TIP
                  </span>
                </div>

                {/* Item 4 */}
                <div className="flex items-start justify-between gap-1.5 pb-1 border-b border-cyan-500/10">
                  <span className="text-blue-200 truncate max-w-[155px]">Your deep-work block is 2-4 PM. Noti...</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-blue-500/30 text-blue-300 bg-blue-950/40 uppercase">
                    TIP
                  </span>
                </div>

                {/* Item 5 */}
                <div className="flex items-start justify-between gap-1.5 pb-1 border-b border-cyan-500/10">
                  <span className="text-emerald-200 truncate max-w-[155px]">CPU usage at 15% System load nominal</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-emerald-500/30 text-emerald-300 bg-emerald-950/40 uppercase">
                    LIVE
                  </span>
                </div>

                {/* Item 6 */}
                <div className="flex items-center justify-between gap-1 pt-0.5">
                  <div className="flex flex-col truncate max-w-[140px]">
                    <span className="text-rose-300 font-semibold text-[10px]">2 tasks overdue</span>
                    <span className="text-[9px] text-rose-400/70 truncate">Review the board and reschedule...</span>
                  </div>
                  <button
                    onClick={() => setShowNewTask(true)}
                    className="px-2 py-0.5 rounded text-[9px] font-mono border border-rose-500/40 bg-rose-950/50 text-rose-300 hover:bg-rose-900/60 transition"
                  >
                    View Tasks
                  </button>
                </div>
              </div>

              <div className="pt-2 text-right">
                <button
                  onClick={() => setShowIntelligence(true)}
                  className="text-[10px] font-mono text-cyan-400/80 hover:text-cyan-200 transition"
                >
                  View All Intelligence &gt;
                </button>
              </div>
            </section>
          </div>

          {/* ── MIDDLE ROW: Active Agents | Mission Timeline | Quick Commands ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-2.5">
            {/* Middle Left: ACTIVE AGENTS (3x2 Grid) */}
            <section className="lg:col-span-5 hud-card p-2.5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono">
                  ACTIVE AGENTS
                </h2>
                <button
                  onClick={() => setShowPalette(true)}
                  className="text-[10px] font-mono text-cyan-400/70 hover:text-cyan-200"
                >
                  View All &gt;
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {/* Agent 1: Coding Agent (Active, Green) */}
                <div className="p-2 rounded-lg border border-emerald-500/30 bg-[#031526]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-emerald-500/40 bg-emerald-950/60 text-emerald-400">
                      <Code2 size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">Coding Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10b981]" />
                        Active
                      </div>
                    </div>
                  </div>
                  {/* Waveform */}
                  <div className="flex items-center gap-0.5 h-3 mt-1.5">
                    {[6, 12, 8, 14, 10, 15, 7, 13, 9].map((h, idx) => (
                      <div
                        key={idx}
                        className="w-0.5 bg-emerald-400/80 rounded-full animate-pulse"
                        style={{ height: `${h}px`, animationDelay: `${idx * 0.1}s` }}
                      />
                    ))}
                  </div>
                </div>

                {/* Agent 2: Research Agent (Active, Cyan) */}
                <div className="p-2 rounded-lg border border-cyan-500/30 bg-[#031526]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-cyan-500/40 bg-cyan-950/60 text-cyan-400">
                      <Search size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">Research Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-cyan-400 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
                        Active
                      </div>
                    </div>
                  </div>
                  {/* Waveform */}
                  <div className="flex items-center gap-0.5 h-3 mt-1.5">
                    {[8, 14, 11, 16, 9, 13, 7, 15, 10].map((h, idx) => (
                      <div
                        key={idx}
                        className="w-0.5 bg-cyan-400/80 rounded-full animate-pulse"
                        style={{ height: `${h}px`, animationDelay: `${idx * 0.12}s` }}
                      />
                    ))}
                  </div>
                </div>

                {/* Agent 3: Memory Agent (Standby, Purple) */}
                <div className="p-2 rounded-lg border border-purple-500/25 bg-[#031322]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-purple-500/40 bg-purple-950/60 text-purple-400">
                      <Database size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">Memory Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-purple-400/80 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
                        Standby
                      </div>
                    </div>
                  </div>
                  {/* Waveform */}
                  <div className="flex items-center gap-0.5 h-3 mt-1.5">
                    {[4, 7, 5, 8, 6, 7, 4, 6, 5].map((h, idx) => (
                      <div
                        key={idx}
                        className="w-0.5 bg-purple-400/60 rounded-full"
                        style={{ height: `${h}px` }}
                      />
                    ))}
                  </div>
                </div>

                {/* Agent 4: Browser Agent (Standby, Yellow) */}
                <div className="p-2 rounded-lg border border-amber-500/25 bg-[#031322]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-amber-500/40 bg-amber-950/60 text-amber-400">
                      <Globe size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">Browser Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-amber-400/80 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        Standby
                      </div>
                    </div>
                  </div>
                  {/* Waveform */}
                  <div className="flex items-center gap-0.5 h-3 mt-1.5">
                    {[5, 9, 6, 10, 7, 8, 5, 9, 6].map((h, idx) => (
                      <div
                        key={idx}
                        className="w-0.5 bg-amber-400/60 rounded-full"
                        style={{ height: `${h}px` }}
                      />
                    ))}
                  </div>
                </div>

                {/* Agent 5: Task Agent (Standby, Blue with Trajectory Dots) */}
                <div className="p-2 rounded-lg border border-blue-500/25 bg-[#031322]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-blue-500/40 bg-blue-950/60 text-blue-400">
                      <CheckSquare size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">Task Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-blue-400/80 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                        Standby
                      </div>
                    </div>
                  </div>
                  {/* Trajectory dots */}
                  <div className="flex items-center gap-1 h-3 mt-1.5">
                    {[1, 2, 3, 4, 5, 6, 7].map((_, idx) => (
                      <div
                        key={idx}
                        className="w-1 h-1 rounded-full bg-blue-400/60"
                        style={{ opacity: 0.3 + idx * 0.1 }}
                      />
                    ))}
                  </div>
                </div>

                {/* Agent 6: System Agent (Standby, Green with Checkmark) */}
                <div className="p-2 rounded-lg border border-emerald-500/25 bg-[#031322]/80 flex flex-col justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1 rounded border border-emerald-500/40 bg-emerald-950/60 text-emerald-400">
                      <ShieldCheck size={12} />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-cyan-100 font-mono">System Agent</div>
                      <div className="flex items-center gap-1 text-[10px] text-emerald-400/80 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        Standby
                      </div>
                    </div>
                  </div>
                  {/* Green checkmark */}
                  <div className="flex items-center justify-end h-3 mt-1.5 pr-1">
                    <Check size={14} className="text-emerald-400 font-bold" />
                  </div>
                </div>
              </div>
            </section>

            {/* Middle Center: MISSION TIMELINE */}
            <section className="lg:col-span-4 hud-card p-2.5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono">
                  MISSION TIMELINE
                </h2>
                <span className="text-[10px] font-mono text-cyan-400/80 border border-cyan-500/25 px-2 py-0.5 rounded bg-[#03162a]">
                  Today ▾
                </span>
              </div>

              <div className="space-y-2.5 font-mono text-xs">
                {/* Milestone 1 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-cyan-400/70 text-[11px]">09:30 am</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
                    <span className="text-cyan-100 font-medium">Daily Standup</span>
                  </div>
                  <span className="text-[10px] text-cyan-400/60 font-semibold">Done</span>
                </div>

                {/* Milestone 2 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-cyan-400/70 text-[11px]">12:00 pm</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00e5ff]" />
                    <span className="text-cyan-100 font-medium truncate max-w-[140px]">Finalize HUD panel spacing</span>
                  </div>
                  <span className="text-[10px] text-cyan-300 font-semibold">In 42 min</span>
                </div>

                {/* Milestone 3 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-cyan-400/70 text-[11px]">02:00 pm</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400/50" />
                    <span className="text-cyan-200/80 font-medium truncate max-w-[140px]">Deep-work block: Voice pipeline</span>
                  </div>
                  <span className="text-[10px] text-cyan-400/60">In 2h 42m</span>
                </div>

                {/* Milestone 4 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-cyan-400/70 text-[11px]">04:30 pm</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400/50" />
                    <span className="text-cyan-200/80 font-medium truncate max-w-[140px]">Design Review — Command Center V1</span>
                  </div>
                  <span className="text-[10px] text-cyan-400/60">In 5h 12m</span>
                </div>
              </div>

              <div className="pt-1.5 text-center">
                <button
                  onClick={() => setShowCalendar(true)}
                  className="text-[10px] font-mono text-cyan-400/80 hover:text-cyan-200 transition"
                >
                  View Full Schedule &gt;
                </button>
              </div>
            </section>

            {/* Middle Right: QUICK COMMANDS */}
            <section className="lg:col-span-3 hud-card p-2.5 flex flex-col justify-between">
              <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono mb-2">
                QUICK COMMANDS
              </h2>

              <div className="space-y-2 font-mono">
                <button
                  onClick={() => setShowNewTask(true)}
                  className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-[#041628]/90 text-cyan-200 text-xs hover:border-cyan-400 hover:bg-cyan-500/15 transition shadow-[0_0_10px_rgba(0,229,255,0.1)]"
                >
                  <Plus size={14} className="text-cyan-400" />
                  <span>Start New Task</span>
                </button>

                <button
                  onClick={() => setShowCalendar(true)}
                  className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-[#041628]/90 text-cyan-200 text-xs hover:border-cyan-400 hover:bg-cyan-500/15 transition shadow-[0_0_10px_rgba(0,229,255,0.1)]"
                >
                  <Calendar size={14} className="text-cyan-400" />
                  <span>Open Calendar</span>
                </button>

                <button
                  onClick={toggleVoice}
                  className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-[#041628]/90 text-cyan-200 text-xs hover:border-cyan-400 hover:bg-cyan-500/15 transition shadow-[0_0_10px_rgba(0,229,255,0.1)]"
                >
                  <Mic size={14} className="text-cyan-400" />
                  <span>Start Voice Chat</span>
                </button>

                <button
                  onClick={() => setShowPalette(true)}
                  className="w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-[#041628]/90 text-cyan-200 text-xs hover:border-cyan-400 hover:bg-cyan-500/15 transition shadow-[0_0_10px_rgba(0,229,255,0.1)]"
                >
                  <Play size={14} className="text-cyan-400" />
                  <span>Run Workflow</span>
                </button>
              </div>
            </section>
          </div>

          {/* ── BOTTOM ROW: System Monitor | Memory Insights | LLM Status ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-2.5 pb-16">
            {/* Bottom Left: SYSTEM MONITOR (3 Radial Gauges) */}
            <section className="lg:col-span-3 hud-card p-2.5 flex flex-col justify-between">
              <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono mb-1">
                SYSTEM MONITOR
              </h2>

              <div className="flex items-center justify-around py-1">
                <RadialGauge label="CPU" value={metrics.cpu} size={70} />
                <RadialGauge label="RAM" value={metrics.ram} size={70} />
                <RadialGauge label="Disk" value={metrics.disk} size={70} />
              </div>

              <div className="text-[10px] font-mono text-center text-cyan-400/60 pt-0.5">
                Hardware nominal · 64 cores active
              </div>
            </section>

            {/* Bottom Center: MEMORY INSIGHTS (Constellation + Stats) */}
            <section className="lg:col-span-4 hud-card p-2.5 flex flex-col justify-between">
              <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono mb-1">
                MEMORY INSIGHTS
              </h2>

              <div className="flex items-center justify-between gap-2">
                {/* Neural Constellation Canvas */}
                <div className="flex-1 flex items-center justify-center">
                  <MemoryConstellation width={170} height={78} />
                </div>

                {/* Stats */}
                <div className="flex flex-col space-y-1 font-mono text-right pr-2">
                  <div>
                    <span className="text-[10px] text-cyan-400/70 block leading-tight">Memories</span>
                    <span className="text-xs font-bold text-cyan-200 leading-none">3,380</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-cyan-400/70 block leading-tight">Session Turns</span>
                    <span className="text-xs font-bold text-cyan-200 leading-none">22</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-cyan-400/70 block leading-tight">Tool Calls</span>
                    <span className="text-xs font-bold text-cyan-200 leading-none">14</span>
                  </div>
                </div>
              </div>

              <div className="text-center pt-0.5">
                <button
                  onClick={() => setShowIntelligence(true)}
                  className="text-[10px] font-mono text-cyan-400/80 hover:text-cyan-200 transition"
                >
                  View Memory Map &gt;
                </button>
              </div>
            </section>

            {/* Bottom Right: LLM STATUS (9 Provider Pills matching screenshot) */}
            <section className="lg:col-span-5 hud-card p-2.5 flex flex-col justify-between">
              <div className="flex items-center justify-between mb-1.5">
                <h2 className="text-xs font-bold tracking-widest text-cyan-300 uppercase font-mono">
                  LLM STATUS
                </h2>
                <span className="text-[10px] font-mono text-cyan-300 font-bold border border-cyan-500/30 px-2 py-0.5 rounded">
                  4 Connected
                </span>
              </div>

              {/* 3x3 Provider Grid */}
              <div className="grid grid-cols-3 gap-1.5 font-mono text-[11px]">
                {/* 1. Claude */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">Claude</span>
                  <span className="text-[9px] text-cyan-400/50">Not Linked</span>
                </div>

                {/* 2. OpenAI */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">OpenAI</span>
                  <span className="text-[9px] text-cyan-400/50">Not Linked</span>
                </div>

                {/* 3. Gemini */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">Gemini</span>
                  <span className="text-[9px] text-cyan-400/50">Not Linked</span>
                </div>

                {/* 4. Groq (Not Linked) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">Groq</span>
                  <span className="text-[9px] text-cyan-400/50">Not Linked</span>
                </div>

                {/* 5. OpenRouter (Not Linked) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">OpenRouter</span>
                  <span className="text-[9px] text-cyan-400/50">Not Linked</span>
                </div>

                {/* 6. Ollama (No Models, Gray) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/15 bg-[#030d1a] flex flex-col justify-between cursor-pointer hover:border-cyan-400/40"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">Ollama</span>
                  <span className="text-[9px] text-cyan-400/50">No Models</span>
                </div>

                {/* 7. Claude Code (Connected, Purple) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-purple-500/30 bg-purple-950/20 flex flex-col justify-between shadow-[0_0_8px_rgba(168,85,247,0.15)] cursor-pointer"
                >
                  <span className="text-purple-200 font-semibold text-[11px]">Claude Code</span>
                  <span className="text-[9px] text-purple-400 flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-purple-400 shadow-[0_0_4px_#a855f7]" />
                    Connected
                  </span>
                </div>

                {/* 8. Cursor (Connected, Cyan) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-cyan-500/30 bg-cyan-950/20 flex flex-col justify-between shadow-[0_0_8px_rgba(0,229,255,0.15)] cursor-pointer"
                >
                  <span className="text-cyan-200 font-semibold text-[11px]">Cursor</span>
                  <span className="text-[9px] text-cyan-400 flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-cyan-400 shadow-[0_0_4px_#00e5ff]" />
                    Connected
                  </span>
                </div>

                {/* 9. Copilot (Connected, Green) */}
                <div
                  onClick={() => setShowProviders(true)}
                  className="p-1.5 rounded border border-emerald-500/30 bg-emerald-950/20 flex flex-col justify-between shadow-[0_0_8px_rgba(16,185,129,0.15)] cursor-pointer"
                >
                  <span className="text-emerald-200 font-semibold text-[11px]">Copilot</span>
                  <span className="text-[9px] text-emerald-400 flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-emerald-400 shadow-[0_0_4px_#10b981]" />
                    Connected
                  </span>
                </div>
              </div>

              <div className="text-center pt-1">
                <button
                  onClick={() => setShowProviders(true)}
                  className="text-[10px] font-mono text-cyan-400/80 hover:text-cyan-200 transition"
                >
                  Manage Providers &gt;
                </button>
              </div>
            </section>
          </div>
        </main>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          4. BOTTOM FLOATING COMMAND DOCK (HUD FOOTER)
      ────────────────────────────────────────────────────────────── */}
      <footer className="fixed bottom-0 left-0 right-0 h-14 border-t border-[#0f3254]/90 bg-[#020d18]/95 backdrop-blur-lg px-4 flex items-center justify-between z-40">
        {/* Left Telemetry: Location, Weather, Network */}
        <div className="flex items-center gap-4 text-xs font-mono text-cyan-300/80">
          <div className="flex items-center gap-1.5">
            <span className="text-cyan-400">📍</span>
            <span>Bhimber, Pak...</span>
          </div>

          <div className="hidden sm:flex items-center gap-1.5">
            <span className="text-amber-400">☀️</span>
            <span>28°C Overcast</span>
          </div>

          <div className="hidden md:flex items-center gap-1.5">
            <Wifi size={14} className="text-emerald-400" />
            <span className="text-emerald-300 font-semibold">Excellent</span>
          </div>
        </div>

        {/* Center: Glowing Oblong Capsule - TALK TO JARVIS */}
        <div className="absolute left-1/2 -translate-x-1/2 flex items-center justify-center">
          <button
            onClick={toggleVoice}
            className="group relative px-7 py-2 rounded-full border-2 border-cyan-400 bg-gradient-to-r from-[#031d36] via-[#08355c] to-[#031d36] shadow-[0_0_25px_rgba(0,229,255,0.7)] hover:shadow-[0_0_35px_rgba(0,229,255,0.9)] hover:scale-105 transition flex items-center gap-3.5"
          >
            {/* Left Soundwaves */}
            <div className="flex items-center gap-0.5 h-4">
              {[6, 12, 18, 10].map((h, i) => (
                <div
                  key={i}
                  className="w-0.5 bg-cyan-300 rounded-full animate-pulse shadow-[0_0_4px_#00e5ff]"
                  style={{ height: `${h}px`, animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>

            {/* Center Text */}
            <div className="flex flex-col items-center">
              <span className="text-xs font-black tracking-[0.2em] text-cyan-100 uppercase font-mono leading-tight">
                TALK TO JARVIS
              </span>
              <span className="text-[9px] font-mono text-cyan-300/80 tracking-wider">
                {live.micActive || isListeningLocal ? "I am listening..." : "Tap to speak"}
              </span>
            </div>

            {/* Right Soundwaves */}
            <div className="flex items-center gap-0.5 h-4">
              {[10, 18, 12, 6].map((h, i) => (
                <div
                  key={i}
                  className="w-0.5 bg-cyan-300 rounded-full animate-pulse shadow-[0_0_4px_#00e5ff]"
                  style={{ height: `${h}px`, animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </button>
        </div>

        {/* Right Controls: Audio Spectrum Dots + Executive Briefing */}
        <div className="flex items-center gap-3">
          {/* Audio spectrum dots */}
          <div className="hidden lg:flex items-center gap-1 opacity-70">
            {Array.from({ length: 14 }).map((_, i) => (
              <div
                key={i}
                className="w-1 h-1 rounded-full bg-cyan-400"
                style={{ opacity: (i % 3 === 0 ? 0.9 : 0.4) }}
              />
            ))}
          </div>

          <button
            onClick={handleExecutiveBriefing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-[#051a30] text-cyan-200 text-xs font-mono hover:border-cyan-400 hover:bg-cyan-500/20 transition shadow-[0_0_12px_rgba(0,229,255,0.2)]"
          >
            <Play size={12} className="text-cyan-300" />
            <span>Executive Briefing</span>
          </button>
        </div>
      </footer>

      {/* ─────────────────────────────────────────────────────────────
          5. INTERACTIVE MODALS
      ────────────────────────────────────────────────────────────── */}
      <NewTaskModal
        isOpen={showNewTask}
        onClose={() => setShowNewTask(false)}
        onSubmit={(title, priority) => {
          live.sendText(`Task queued: ${title} (Priority: ${priority})`);
        }}
      />

      <CalendarModal isOpen={showCalendar} onClose={() => setShowCalendar(false)} />
      <IntelligenceModal isOpen={showIntelligence} onClose={() => setShowIntelligence(false)} />
      <ManageProvidersModal isOpen={showProviders} onClose={() => setShowProviders(false)} />
      <ExecutiveBriefingModal isOpen={showBriefing} onClose={() => setShowBriefing(false)} />
      <CommandPaletteModal
        isOpen={showPalette}
        onClose={() => setShowPalette(false)}
        onSelectAction={(action) => {
          if (action === "new_task") setShowNewTask(true);
          if (action === "open_calendar") setShowCalendar(true);
          if (action === "voice_chat") toggleVoice();
          if (action === "run_workflow") setShowPalette(true);
          if (action === "memory_map") setShowIntelligence(true);
          if (action === "manage_providers") setShowProviders(true);
          if (action === "executive_briefing") handleExecutiveBriefing();
        }}
      />
    </div>
  );
}
