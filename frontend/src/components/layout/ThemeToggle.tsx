"use client";

import { useLayoutEffect, useSyncExternalStore } from "react";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  applyThemePreference,
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

// The server cannot know the stored choice; "system" there avoids a hydration mismatch.
const useThemePreference = (): ThemePreference =>
  useSyncExternalStore(subscribeThemePreference, readThemePreference, () => "system");

/**
 * Mounted once in the root layout. `themeInitScript` sets `.dark` before the first paint, but
 * React may re-render <html> on the client (e.g. a 404 in dev) and drop the class: re-apply it
 * from storage, and follow the OS while the choice is "system".
 */
export function ThemeSync() {
  const preference = useThemePreference();
  useLayoutEffect(() => {
    applyThemePreference(readThemePreference());
    return preference === "system" ? followSystemTheme() : undefined;
  }, [preference]);
  return null;
}

/** Sistema / Claro / Escuro. */
export function ThemeToggle() {
  const preference = useThemePreference();

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
