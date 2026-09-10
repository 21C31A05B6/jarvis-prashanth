"use client";

import { FormEvent, useEffect, useState } from "react";
import { Brain, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type MemoryEntryItem, type MemorySearchResult } from "@/lib/api";

const CATEGORIES = ["identity", "preferences", "projects", "relationships", "wishes", "notes", "short_term"];

export function MemoryPanel() {
  const [entries, setEntries] = useState<MemoryEntryItem[]>([]);
  const [category, setCategory] = useState("notes");
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MemorySearchResult[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setEntries(await api<MemoryEntryItem[]>("/memory"));
    } catch {
      /* transient — user will see stale list, not worth a hard error here */
    }
  }

  useEffect(() => {
    api<MemoryEntryItem[]>("/memory").then(setEntries).catch(() => undefined);
  }, []);

  async function addEntry(event: FormEvent) {
    event.preventDefault();
    if (!key.trim() || !value.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api("/memory", { method: "PUT", body: JSON.stringify({ category, key: key.trim(), value: value.trim() }) });
      setKey("");
      setValue("");
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save that memory.");
    } finally {
      setBusy(false);
    }
  }

  async function removeEntry(entry: MemoryEntryItem) {
    await api(`/memory/${entry.category}/${encodeURIComponent(entry.key)}`, { method: "DELETE" }).catch(() => undefined);
    await refresh();
  }

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      setSearchResults(await api<MemorySearchResult[]>("/memory/search", { method: "POST", body: JSON.stringify({ query: query.trim() }) }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search needs a configured Gemini key.");
    } finally {
      setBusy(false);
    }
  }

  const shown = searchResults ?? entries;

  return (
    <section className="agent-panel" aria-labelledby="memory-panel-title">
      <div className="capability-heading">
        <span id="memory-panel-title"><Brain size={12} style={{ marginRight: 6, display: "inline" }} />Memory</span>
        <b>{String(entries.length).padStart(2, "0")}</b>
      </div>

      <form className="memory-search" onSubmit={runSearch}>
        <input value={query} onChange={(event) => { setQuery(event.target.value); if (!event.target.value) setSearchResults(null); }} placeholder="Search memory by meaning..." aria-label="Search memory" />
        <Button type="submit" variant="ghost" size="icon" aria-label="Search" disabled={!query.trim() || busy}><Search size={14} /></Button>
      </form>

      <ul className="memory-list">
        {shown.length === 0 && <li className="agent-empty">Nothing here yet.</li>}
        {shown.map((entry) => (
          <li key={`${entry.category}-${entry.key}`} className="memory-item">
            <div>
              <span className="memory-category">{entry.category.replaceAll("_", " ")}</span>
              <b>{entry.key.replaceAll("_", " ")}</b>
              {"score" in entry && <i className="memory-score">{Math.round((entry as MemorySearchResult).score * 100)}%</i>}
            </div>
            <p>{entry.value}</p>
            <button type="button" aria-label={`Forget ${entry.key}`} onClick={() => removeEntry(entry)}><Trash2 size={12} /></button>
          </li>
        ))}
      </ul>

      <form className="memory-add" onSubmit={addEntry}>
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Memory category">
          {CATEGORIES.map((cat) => <option key={cat} value={cat}>{cat.replaceAll("_", " ")}</option>)}
        </select>
        <input value={key} onChange={(event) => setKey(event.target.value)} placeholder="Key (e.g. favorite_editor)" aria-label="Memory key" />
        <input value={value} onChange={(event) => setValue(event.target.value)} placeholder="Value" aria-label="Memory value" />
        <Button type="submit" size="sm" disabled={!key.trim() || !value.trim() || busy}>Remember</Button>
      </form>
      {error && <p className="console-error" role="alert">{error}</p>}
    </section>
  );
}
