"use client";

import { FormEvent, useEffect, useState } from "react";
import { Bell, CheckSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Notification, type Todo } from "@/lib/api";

export function TodoPanel() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    api<Todo[]>("/todos").then(setTodos).catch(() => undefined);
  }, []);

  async function refresh() {
    setTodos(await api<Todo[]>("/todos").catch(() => []));
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    await api("/todos", { method: "POST", body: JSON.stringify({ text: draft.trim() }) });
    setDraft("");
    await refresh();
  }

  async function toggle(todo: Todo) {
    await api(`/todos/${todo.id}/done?done=${!todo.done}`, { method: "PUT" });
    await refresh();
  }

  async function remove(todo: Todo) {
    await api(`/todos/${todo.id}`, { method: "DELETE" });
    await refresh();
  }

  return (
    <section className="agent-panel" aria-labelledby="todo-panel-title">
      <div className="capability-heading">
        <span id="todo-panel-title"><CheckSquare size={12} style={{ marginRight: 6, display: "inline" }} />To-dos</span>
        <b>{String(todos.filter((t) => !t.done).length).padStart(2, "0")}</b>
      </div>
      <ul className="memory-list">
        {todos.length === 0 && <li className="agent-empty">Nothing on your list.</li>}
        {todos.map((todo) => (
          <li key={todo.id} className="memory-item">
            <div>
              <label style={{ display: "flex", alignItems: "center", gap: ".4rem", cursor: "pointer" }}>
                <input type="checkbox" checked={todo.done} onChange={() => toggle(todo)} />
                <b style={{ textDecoration: todo.done ? "line-through" : "none" }}>{todo.text}</b>
              </label>
            </div>
            <button type="button" aria-label={`Delete ${todo.text}`} onClick={() => remove(todo)}><Trash2 size={12} /></button>
          </li>
        ))}
      </ul>
      <form className="memory-search" onSubmit={add}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Add a to-do..." aria-label="New to-do" />
        <Button type="submit" size="sm" disabled={!draft.trim()}>Add</Button>
      </form>
    </section>
  );
}

export function NotificationsPanel() {
  const [notifications, setNotifications] = useState<Notification[]>([]);

  useEffect(() => {
    api<Notification[]>("/notifications").then(setNotifications).catch(() => undefined);
  }, []);

  async function refresh() {
    setNotifications(await api<Notification[]>("/notifications").catch(() => []));
  }

  async function markRead(notification: Notification) {
    await api(`/notifications/${notification.id}/read`, { method: "POST" });
    await refresh();
  }

  async function remove(notification: Notification) {
    await api(`/notifications/${notification.id}`, { method: "DELETE" });
    await refresh();
  }

  const unread = notifications.filter((n) => !n.read_at).length;

  return (
    <section className="agent-panel" aria-labelledby="notif-panel-title">
      <div className="capability-heading">
        <span id="notif-panel-title"><Bell size={12} style={{ marginRight: 6, display: "inline" }} />Notifications</span>
        <b>{String(unread).padStart(2, "0")}</b>
      </div>
      <ul className="memory-list">
        {notifications.length === 0 && <li className="agent-empty">No notifications yet.</li>}
        {notifications.map((notification) => (
          <li key={notification.id} className="memory-item" style={{ opacity: notification.read_at ? 0.55 : 1 }}>
            <div>
              <b>{notification.title}</b>
            </div>
            <p>{notification.body}</p>
            <button type="button" aria-label={`Dismiss ${notification.title}`} onClick={() => remove(notification)}><Trash2 size={12} /></button>
            {!notification.read_at && (
              <Button type="button" size="sm" variant="ghost" onClick={() => markRead(notification)}>Mark read</Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
