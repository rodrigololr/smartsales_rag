"use client";

import React from "react";
import { RotateCcw } from "lucide-react";

export interface ResetSessionButtonProps {
  onReset: () => void;
  disabled?: boolean;
}

export const ResetSessionButton: React.FC<ResetSessionButtonProps> = ({
  onReset,
  disabled = false,
}) => {
  return (
    <button
      type="button"
      data-testid="reset-session-btn"
      onClick={onReset}
      disabled={disabled}
      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      title="Reiniciar conversa (limpar contexto atual)"
      aria-label="Reiniciar conversa"
    >
      <RotateCcw className="w-4 h-4" />
    </button>
  );
};
