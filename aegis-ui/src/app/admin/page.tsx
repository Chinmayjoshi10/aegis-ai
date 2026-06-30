"use client";

import { AppShell } from "@/components/layout/AppShell";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { Users, Shield, Building, Settings, FileCheck, Activity } from "lucide-react";

const tabs = [
  { id: "team", label: "Team", icon: Users },
  { id: "roles", label: "Roles", icon: Shield },
  { id: "clients", label: "Clients", icon: Building },
  { id: "metrics", label: "Metrics", icon: Settings },
  { id: "compliance", label: "Compliance", icon: FileCheck },
  { id: "audit", label: "Audit Log", icon: Activity },
];

const teamMembers = [
  { name: "James Smith", email: "j.smith@company.com", role: "Admin", access: "Full", lastLogin: "2h ago", status: "online" },
  { name: "Alice Chen", email: "a.chen@company.com", role: "Analyst", access: "Read/Write", lastLogin: "1d ago", status: "offline" },
  { name: "Mike Johnson", email: "m.johnson@company.com", role: "Viewer", access: "Read Only", lastLogin: "3d ago", status: "offline" },
];

const metricDefs = [
  { name: "Revenue", polarity: "▲ Higher is better", range: "0 – ∞", compliance: "SOX Required" },
  { name: "Cost", polarity: "▼ Lower is better", range: "0 – ∞", compliance: "—" },
  { name: "Conversion Rate", polarity: "▲ Higher is better", range: "0% – 100%", compliance: "—" },
  { name: "NPS", polarity: "▲ Higher is better", range: "-100 – 100", compliance: "GDPR" },
  { name: "CAC", polarity: "▼ Lower is better", range: "0 – ∞", compliance: "—" },
];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState("team");

  return (
    <AppShell>
      <div className="space-y-6 max-w-6xl">
        <div>
          <h1 className="text-xl font-semibold mb-1">Admin & Governance</h1>
          <p className="text-sm text-[#64748B]">Team management, roles, compliance, and metric governance.</p>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-[#2A2F3A]">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)} className={cn("flex items-center gap-2 px-4 py-2.5 text-xs font-medium transition-all border-b-2 -mb-[1px]", activeTab === id ? "border-[#A855F7] text-[#F8FAFC]" : "border-transparent text-[#64748B] hover:text-[#94A3B8]")}>
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>

        {/* Team Tab */}
        {activeTab === "team" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Team Members ({teamMembers.length})</h2>
              <button className="px-4 py-2 text-xs font-medium bg-[#A855F7] text-white rounded hover:bg-[#9333EA] transition-colors">+ Invite Member</button>
            </div>
            <div className="card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#2A2F3A] text-[#64748B]">
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Name</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Role</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Access</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Last Login</th>
                    <th className="text-center px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {teamMembers.map((m) => (
                    <tr key={m.email} className="border-b border-[#2A2F3A]/50 hover:bg-[#1A1F2E] transition-colors cursor-pointer">
                      <td className="px-4 py-3">
                        <div className="text-[#F8FAFC] font-medium">{m.name}</div>
                        <div className="text-[10px] text-[#64748B] font-mono">{m.email}</div>
                      </td>
                      <td className="px-4 py-3 text-[#94A3B8]">{m.role}</td>
                      <td className="px-4 py-3 text-[#94A3B8]">{m.access}</td>
                      <td className="px-4 py-3 font-mono text-[#64748B]">{m.lastLogin}</td>
                      <td className="px-4 py-3 text-center">
                        <div className={cn("w-2 h-2 rounded-full mx-auto", m.status === "online" ? "bg-emerald-500" : "bg-[#3A4150]")} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Metrics Tab */}
        {activeTab === "metrics" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Metric Governance</h2>
              <button className="px-4 py-2 text-xs font-medium border border-[#2A2F3A] text-[#94A3B8] rounded hover:border-[#3A4150] transition-colors">+ Define Metric</button>
            </div>
            <div className="card overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-[#2A2F3A] text-[#64748B]">
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Metric</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Polarity</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Range</th>
                    <th className="text-left px-4 py-3 font-mono font-medium uppercase text-[10px] tracking-wider">Compliance</th>
                  </tr>
                </thead>
                <tbody>
                  {metricDefs.map((m) => (
                    <tr key={m.name} className="border-b border-[#2A2F3A]/50 hover:bg-[#1A1F2E] transition-colors cursor-pointer">
                      <td className="px-4 py-3 text-[#F8FAFC] font-medium">{m.name}</td>
                      <td className="px-4 py-3 text-[#94A3B8]">{m.polarity}</td>
                      <td className="px-4 py-3 font-mono text-[#64748B]">{m.range}</td>
                      <td className="px-4 py-3">{m.compliance !== "—" ? <span className="px-2 py-0.5 text-[9px] font-mono border border-amber-500/30 text-amber-400 bg-amber-500/10 rounded">{m.compliance}</span> : <span className="text-[#334155]">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Other tabs - placeholder */}
        {!["team", "metrics"].includes(activeTab) && (
          <div className="card p-12 text-center">
            <p className="text-sm text-[#64748B]">{tabs.find((t) => t.id === activeTab)?.label} management coming soon.</p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
