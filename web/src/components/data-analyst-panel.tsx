"use client";

import { FormEvent, useState } from "react";
import { BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type DataAnalyzeResult } from "@/lib/api";

export function DataAnalystPanel() {
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<DataAnalyzeResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function analyze(event: FormEvent) {
    event.preventDefault();
    if (!csv.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api<DataAnalyzeResult>("/data/analyze", { method: "POST", body: JSON.stringify({ csv_text: csv }) }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not analyze that data.");
    } finally {
      setBusy(false);
    }
  }

  const chart = result?.chart;
  const maxValue = chart ? Math.max(...chart.values, 1) : 1;

  return (
    <section className="agent-panel" aria-labelledby="data-panel-title">
      <div className="capability-heading">
        <span id="data-panel-title"><BarChart3 size={12} style={{ marginRight: 6, display: "inline" }} />Data analyst</span>
      </div>
      <form className="agent-composer" onSubmit={analyze}>
        <textarea
          value={csv}
          onChange={(event) => setCsv(event.target.value)}
          placeholder="Paste CSV data here..."
          aria-label="CSV data"
          rows={3}
        />
        <Button type="submit" size="icon" aria-label="Analyze" disabled={!csv.trim() || busy}><BarChart3 size={16} /></Button>
      </form>

      {result && (
        <div className="task-card">
          <div className="task-card-heading">
            <span>{result.row_count} rows × {result.column_count} columns</span>
          </div>
          {chart && (
            <div className="data-chart" role="img" aria-label={chart.title}>
              {chart.labels.map((label, index) => (
                <div key={label + index} className="data-chart-bar">
                  <div className="data-chart-bar-fill" style={{ height: `${(chart.values[index] / maxValue) * 100}%` }} />
                  <span>{label}</span>
                </div>
              ))}
            </div>
          )}
          <ul className="agent-plan">
            {result.columns.map((column) => (
              <li key={column.name}>
                <span>
                  <b>{column.name}</b> ({column.dtype}) —{" "}
                  {column.mean !== null && column.mean !== undefined
                    ? `mean ${column.mean.toFixed(2)}, range ${column.min}–${column.max}`
                    : column.top_values?.map((v) => `${v.value} (${v.count})`).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className="console-error" role="alert">{error}</p>}
    </section>
  );
}
