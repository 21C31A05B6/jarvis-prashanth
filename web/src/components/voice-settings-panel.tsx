"use client";

import { useEffect, useState } from "react";
import { Mic2 } from "lucide-react";
import { api } from "@/lib/api";

type VoiceOption = { id: string; name: string };
type VoiceSettings = { voice_id: string; language: string | null; available_voices: VoiceOption[] };

export function VoiceSettingsPanel() {
  const [settings, setSettings] = useState<VoiceSettings | null>(null);
  const [language, setLanguage] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api<VoiceSettings>("/voice/settings").then((data) => {
      setSettings(data);
      setLanguage(data.language ?? "");
    }).catch(() => undefined);
  }, []);

  async function updateVoice(voiceId: string) {
    const updated = await api<VoiceSettings>("/voice/settings", { method: "PUT", body: JSON.stringify({ voice_id: voiceId }) });
    setSettings(updated);
    flashSaved();
  }

  async function commitLanguage() {
    const updated = await api<VoiceSettings>("/voice/settings", { method: "PUT", body: JSON.stringify({ language: language || null }) });
    setSettings(updated);
    flashSaved();
  }

  function flashSaved() {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  if (!settings) return null;

  return (
    <section className="agent-panel" aria-labelledby="voice-panel-title">
      <div className="capability-heading">
        <span id="voice-panel-title"><Mic2 size={12} style={{ marginRight: 6, display: "inline" }} />Voice &amp; language</span>
        {saved && <b className="voice-saved">saved</b>}
      </div>
      <div className="voice-grid">
        <label htmlFor="voice-select">Personality</label>
        <select id="voice-select" value={settings.voice_id} onChange={(event) => updateVoice(event.target.value)}>
          {settings.available_voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
        </select>
        <label htmlFor="voice-language">Preferred language</label>
        <input
          id="voice-language"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
          onBlur={commitLanguage}
          placeholder="Auto-detect (e.g. Hindi, Tamil, English)"
        />
      </div>
    </section>
  );
}
