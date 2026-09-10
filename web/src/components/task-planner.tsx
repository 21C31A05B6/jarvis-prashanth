"use client";

import { FormEvent, useState } from "react";
import { ListTree, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Task } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  planned: "Planned",
  completed: "Completed",
  partial: "Partially run",
  failed: "Failed",
  skipped_desktop_only: "Desktop only",
};

export function TaskPlanner() {
  const [goal, setGoal] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function plan(event: FormEvent) {
    event.preventDefault();
    if (!goal.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const created = await api<Task>("/planner/plan", { method: "POST", body: JSON.stringify({ goal: goal.trim() }) });
      setTask(created);
      setGoal("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not generate a plan.");
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!task || busy) return;
    setBusy(true);
    setError("");
    try {
      setTask(await api<Task>(`/tasks/${task.task_id}/run`, { method: "POST" }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not run the task.");
    } finally {
      setBusy(false);
    }
  }

  const canRun = task && ["planned", "partial", "failed"].includes(task.status);

  return (
    <section className="agent-panel" aria-labelledby="planner-panel-title">
      <div className="capability-heading">
        <span id="planner-panel-title"><ListTree size={12} style={{ marginRight: 6, display: "inline" }} />Task planner</span>
      </div>

      <form className="agent-composer" onSubmit={plan}>
        <textarea value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="Describe a goal to break into steps..." aria-label="Task goal" rows={2} />
        <Button type="submit" size="icon" aria-label="Generate plan" disabled={!goal.trim() || busy}><ListTree size={16} /></Button>
      </form>

      {task && (
        <div className="task-card">
          <div className="task-card-heading">
            <span>{task.goal}</span>
            <b data-status={task.status}>{STATUS_LABEL[task.status] ?? task.status}</b>
          </div>
          <ol className="agent-plan">
            {task.steps.map((step) => (
              <li key={step.step}>
                <span>
                  <b>{step.tool}</b> — {step.description}
                </span>
                {step.status !== "pending" && (
                  <p className="task-step-output" data-status={step.status}>{step.output}</p>
                )}
              </li>
            ))}
          </ol>
          {canRun && (
            <Button type="button" size="sm" variant="secondary" onClick={run} disabled={busy}>
              <Play size={13} /> Run hosted-safe steps
            </Button>
          )}
        </div>
      )}
      {error && <p className="console-error" role="alert">{error}</p>}
    </section>
  );
}
