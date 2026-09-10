"use client";

import { useEffect, useState } from "react";
import { ListVideo, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

type WorkflowStep = { tool: string; parameters: Record<string, unknown> };
type Workflow = { id: string; name: string; steps: WorkflowStep[]; created_at: string };

export function WorkflowsPanel() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);

  async function refresh() {
    setWorkflows(await api<Workflow[]>("/workflows").catch(() => []));
  }

  useEffect(() => {
    api<Workflow[]>("/workflows").then(setWorkflows).catch(() => undefined);
  }, []);

  async function remove(id: string) {
    await api(`/workflows/${id}`, { method: "DELETE" }).catch(() => undefined);
    await refresh();
  }

  return (
    <section className="agent-panel" aria-labelledby="workflows-panel-title">
      <div className="capability-heading">
        <span id="workflows-panel-title"><ListVideo size={12} style={{ marginRight: 6, display: "inline" }} />Workflows</span>
        <b>{String(workflows.length).padStart(2, "0")}</b>
      </div>
      {workflows.length === 0 ? (
        <p className="agent-empty">
          Say &ldquo;start recording&rdquo; to JARVIS on desktop, do a sequence of actions, then
          &ldquo;stop recording&rdquo; — it&rsquo;ll show up here. Replaying a workflow also happens
          on desktop, since the steps are things like opening apps and controlling your screen.
        </p>
      ) : (
        <ul className="memory-list">
          {workflows.map((workflow) => (
            <li key={workflow.id} className="memory-item">
              <div>
                <b>{workflow.name}</b>
                <i className="memory-score">{workflow.steps.length} steps</i>
              </div>
              <p>{workflow.steps.map((step) => step.tool).join(" → ")}</p>
              <button type="button" aria-label={`Delete ${workflow.name}`} onClick={() => remove(workflow.id)}>
                <Trash2 size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
