"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  followSystemTheme,
  readThemePreference,
  selectThemePreference,
  subscribeThemePreference,
  type ThemePreference,
} from "@/lib/theme";
import { cn } from "@/lib/utils";

const OPTIONS: { value: ThemePreference; label: string; icon: LucideIcon }[] = [
  { value: "system", label: "Tema do sistema", icon: Monitor },
  { value: "light", label: "Tema claro", icon: Sun },
  { value: "dark", label: "Tema escuro", icon: Moon },
];

/** Sistema / Claro / Escuro. The first paint is handled by `themeInitScript` in the root layout. */
export function ThemeToggle() {
  // The server cannot know the stored choice; "system" there avoids a hydration mismatch.
  const preference = useSyncExternalStore(subscribeThemePreference, readThemePreference, () => "system");

  useEffect(() => (preference === "system" ? followSystemTheme() : undefined), [preference]);

  return (
    <div role="group" aria-label="Tema" className="flex items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <Button
          key={value}
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-pressed={preference === value}
          aria-label={label}
          title={label}
          onClick={() => selectThemePreference(value)}
          className={cn(
            preference === value
              ? "bg-background text-foreground shadow-xs hover:bg-background dark:hover:bg-background"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon aria-hidden />
        </Button>
      ))}
    </div>
  );
}
