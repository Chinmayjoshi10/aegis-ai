import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function formatCurrency(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function getRelativeTime(date: string): string {
  const diff = Date.now() - new Date(date).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function getPriorityColor(priority: string): string {
  switch (priority) {
    case "CRITICAL": return "text-red-400 border-red-500/30 bg-red-500/10";
    case "HIGH": return "text-amber-400 border-amber-500/30 bg-amber-500/10";
    case "MEDIUM": return "text-blue-400 border-blue-500/30 bg-blue-500/10";
    case "LOW": return "text-slate-400 border-slate-500/30 bg-slate-500/10";
    default: return "text-slate-400 border-slate-500/30 bg-slate-500/10";
  }
}

export function getSignalColor(direction: string): string {
  switch (direction) {
    case "UP": return "text-emerald-400";
    case "DOWN": return "text-red-400";
    case "FLAT": return "text-slate-500";
    default: return "text-slate-500";
  }
}

export function getConfidenceColor(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 50) return "bg-amber-500";
  return "bg-red-500";
}
