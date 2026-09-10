"use client";

import { FormEvent, useState } from "react";
import { Bug, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type Mode = "debug" | "tests" | "command";

export function DevToolsPanel() {
  const [mode, setMode] = useState<Mode>("debug");
  const [codeOrTask, setCodeOrTask] = useState("");
  const [error2, setError2] = useState("");
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!codeOrTask.trim() || busy) return;
    setBusy(true);
    setError("");
    setOutput("");
    try {
      if (mode === "debug") {
        const result = await api<{ explanation: string; fix: string }>("/dev/debug", {
          method: "POST", body: JSON.stringify({ code: codeOrTask, error: error2 || "unknown error", language: "python" }),
        });
        setOutput(`${result.explanation}\n\n${result.fix}`);
      } else if (mode === "tests") {
        const result = await api<{ tests: string; framework: string }>("/dev/generate-tests", {
          method: "POST", body: JSON.stringify({ code: codeOrTask, language: "python" }),
        });
        setOutput(`// ${result.framework}\n${result.tests}`);
      } else {
        const result = await api<{ command: string; explanation: string; caution: string }>("/dev/suggest-command", {
          method: "POST", body: JSON.stringify({ task: codeOrTask, shell: "bash" }),
        });
        setOutput(`$ ${result.command}\n\n${result.explanation}${result.caution ? `\n\n⚠ ${result.caution}` : ""}`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "That didn't work.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="agent-panel" aria-labelledby="dev-panel-title">
      <div className="capability-heading">
        <span id="dev-panel-title"><Bug size={12} style={{ marginRight: 6, display: "inline" }} />Dev tools</span>
      </div>
      <div className="agent-pills" role="tablist" aria-label="Dev tool mode">
        {(["debug", "tests", "command"] as Mode[]).map((option) => (
          <button key={option} type="button" role="tab" aria-selected={mode === option} className="agent-pill" onClick={() => { setMode(option); setOutput(""); }}>
            {option === "command" ? <Terminal size={11} /> : null} {option}
          </button>
        ))}
      </div>
      <form className="agent-composer" style={{ flexDirection: "column" }} onSubmit={submit}>
        <textarea
          value={codeOrTask}
          onChange={(event) => setCodeOrTask(event.target.value)}
          placeholder={mode === "command" ? "Describe the task (e.g. find large files)..." : "Paste code..."}
          aria-label="Input"
          rows={3}
        />
        {mode === "debug" && (
          <input
            value={error2}
            onChange={(event) => setError2(event.target.value)}
            placeholder="Error message"
            aria-label="Error message"
            style={{ border: "1px solid var(--line)", background: "var(--surface)", borderRadius: ".35rem", padding: ".4rem .5rem", color: "var(--ink)", fontSize: ".68rem" }}
          />
        )}
        <Button type="submit" size="sm" disabled={!codeOrTask.trim() || busy}>{busy ? "Working..." : "Run"}</Button>
      </form>
      {output && <pre className="task-step-output" style={{ margin: "0 1.2rem 1rem", whiteSpace: "pre-wrap" }}>{output}</pre>}
      {error && <p className="console-error" role="alert">{error}</p>}
    </section>
  );
}
