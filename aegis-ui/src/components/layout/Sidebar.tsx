"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAegisStore } from "@/store/aegisStore";
import { LayoutDashboard, Zap, Grid3X3, MessageSquare, Link2, FileBarChart, Settings, Shield } from "lucide-react";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/dashboard" },
  { icon: Zap, label: "Decisions", href: "/decisions" },
  { icon: Grid3X3, label: "Segments", href: "/segments" },
  { icon: MessageSquare, label: "Analyst", href: "/analyst" },
  { icon: Link2, label: "Integrations", href: "/integrations" },
  { icon: FileBarChart, label: "Reports", href: "/reports" },
  { icon: Settings, label: "Admin", href: "/admin" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarExpanded, setSidebarExpanded } = useAegisStore();

  return (
    <aside
      onMouseEnter={() => setSidebarExpanded(true)}
      onMouseLeave={() => setSidebarExpanded(false)}
      className={cn(
        "fixed left-0 top-0 h-screen bg-[#05070D] border-r border-[#2A2F3A] flex flex-col z-40 transition-all duration-200",
        sidebarExpanded ? "w-[240px]" : "w-16"
      )}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-[#2A2F3A]">
        <Shield className="w-6 h-6 text-[#A855F7] shrink-0" />
        <span className={cn("ml-3 font-bold text-sm tracking-[0.2em] text-[#F8FAFC] transition-opacity duration-200 whitespace-nowrap", sidebarExpanded ? "opacity-100" : "opacity-0 w-0 overflow-hidden")}>
          AEGIS
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 flex flex-col gap-1 px-2">
        {navItems.map(({ icon: Icon, label, href }) => {
          const active = pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded transition-all duration-200 group relative",
                active
                  ? "bg-[#A855F7]/10 text-[#A855F7]"
                  : "text-[#64748B] hover:text-[#94A3B8] hover:bg-[#1A1F2E]"
              )}
            >
              {active && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-[#A855F7] rounded-r" />}
              <Icon className="w-5 h-5 shrink-0" />
              <span className={cn("text-sm font-medium whitespace-nowrap transition-opacity duration-200", sidebarExpanded ? "opacity-100" : "opacity-0 w-0 overflow-hidden")}>
                {label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* System Mode */}
      <div className="p-3 border-t border-[#2A2F3A]">
        <div className={cn("flex items-center gap-2 transition-opacity duration-200", sidebarExpanded ? "opacity-100" : "opacity-0")}>
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[10px] font-mono text-[#64748B] uppercase whitespace-nowrap">System Online</span>
        </div>
      </div>
    </aside>
  );
}
