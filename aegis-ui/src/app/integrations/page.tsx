"use client";

import { AppShell } from "@/components/layout/AppShell";
import { UploadWorkflow } from "@/components/upload/UploadWorkflow";
import { mockIntegrations } from "@/lib/mockData";
import { cn } from "@/lib/utils";
import { Check, Clock, Link2 } from "lucide-react";
import { useRouter } from "next/navigation";

const iconMap: Record<string, string> = { csv: "📄", excel: "📊", shopify: "🛒", meta: "📱", google_ads: "🔍", crm: "👥", erp: "🏢" };

export default function IntegrationsPage() {
  const router = useRouter();
  const connected = mockIntegrations.filter((i) => i.status === "connected");
  const available = mockIntegrations.filter((i) => i.status === "available");
  const coming = mockIntegrations.filter((i) => i.status === "coming_soon");

  return (
    <AppShell>
      <div className="space-y-8 max-w-5xl">
        <div>
          <h1 className="text-xl font-semibold mb-1">Integration Hub</h1>
          <p className="text-sm text-[#64748B]">Connect your data sources. AEGIS handles the rest.</p>
        </div>

        {/* Live Upload */}
        <UploadWorkflow onComplete={() => router.push("/dashboard")} />

        {/* Connected */}
        {connected.length > 0 && (
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4 flex items-center gap-2"><Check className="w-3.5 h-3.5 text-emerald-500" /> Connected ({connected.length})</h2>
            <div className="grid grid-cols-3 gap-4">
              {connected.map((int) => (
                <div key={int.id} className="card p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-2xl">{iconMap[int.type]}</span>
                    <div className="flex items-center gap-1.5"><div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" /><span className="text-[10px] font-mono text-emerald-400">Active</span></div>
                  </div>
                  <h3 className="text-sm font-medium mb-1">{int.name}</h3>
                  {int.lastSync && <p className="text-[10px] font-mono text-[#64748B]">Last sync: 2m ago</p>}
                  <button className="mt-3 w-full py-1.5 text-[11px] font-mono border border-[#2A2F3A] rounded text-[#94A3B8] hover:border-[#3A4150] hover:text-[#F8FAFC] transition-colors">Configure</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Available */}
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4 flex items-center gap-2"><Link2 className="w-3.5 h-3.5 text-blue-500" /> Available ({available.length})</h2>
          <div className="grid grid-cols-3 gap-4">
            {available.map((int) => (
              <div key={int.id} className="card p-4">
                <span className="text-2xl block mb-3">{iconMap[int.type]}</span>
                <h3 className="text-sm font-medium mb-3">{int.name}</h3>
                <button className="w-full py-1.5 text-[11px] font-mono bg-[#A855F7]/10 border border-[#A855F7]/30 rounded text-[#A855F7] hover:bg-[#A855F7]/20 transition-colors">Set Up</button>
              </div>
            ))}
          </div>
        </div>

        {/* Coming Soon */}
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4 flex items-center gap-2"><Clock className="w-3.5 h-3.5 text-[#64748B]" /> Coming Soon ({coming.length})</h2>
          <div className="grid grid-cols-3 gap-4">
            {coming.map((int) => (
              <div key={int.id} className="card p-4 opacity-50">
                <span className="text-2xl block mb-3">{iconMap[int.type]}</span>
                <h3 className="text-sm font-medium mb-3">{int.name}</h3>
                <button disabled className="w-full py-1.5 text-[11px] font-mono border border-[#2A2F3A] rounded text-[#334155] cursor-not-allowed">Notify Me</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
