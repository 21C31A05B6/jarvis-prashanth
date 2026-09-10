"use client";

import { useEffect, useState } from "react";
import { Palette } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type Theme = "terminal" | "glass" | "light";
const THEMES: Theme[] = ["terminal", "glass", "light"];

export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>("terminal");

  useEffect(() => {
    api<{ theme: Theme }>("/preferences/theme")
      .then((data) => {
        setTheme(data.theme);
        document.documentElement.dataset.theme = data.theme;
      })
      .catch(() => undefined);
  }, []);

  async function cycle() {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    setTheme(next);
    document.documentElement.dataset.theme = next;
    await api("/preferences/theme", { method: "PUT", body: JSON.stringify({ theme: next }) }).catch(() => undefined);
  }

  return (
    <Button variant="ghost" size="sm" onClick={cycle} aria-label={`Switch theme (current: ${theme})`} title={`Theme: ${theme}`}>
      <Palette size={14} /> {theme}
    </Button>
  );
}
