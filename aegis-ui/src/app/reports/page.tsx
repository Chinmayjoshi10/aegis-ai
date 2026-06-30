"use client";

import { AppShell } from "@/components/layout/AppShell";
import { cn } from "@/lib/utils";
import { useState } from "react";
import { FileText, Presentation, Download, Calendar, Star } from "lucide-react";

const templates = [
  { id: "exec-monthly", name: "Executive Monthly", desc: "Comprehensive monthly performance review with decision audit trail.", icon: FileText, starred: true },
  { id: "investor-deck", name: "Investor Deck", desc: "Board-ready presentation with KPI trends and strategic recommendations.", icon: Presentation, starred: false },
  { id: "campaign-perf", name: "Campaign Performance", desc: "Channel-level analysis with segment breakdowns and signal history.", icon: FileText, starred: false },
  { id: "segment-deep", name: "Segment Deep Dive", desc: "Granular segment analysis with cross-metric correlations.", icon: FileText, starred: false },
];

const recentReports = [
  { name: "April Executive Report", format: "PDF", size: "2.3 MB", date: "Apr 30, 2026" },
  { name: "Q1 Investor Deck", format: "PPT", size: "4.1 MB", date: "Apr 1, 2026" },
  { name: "March Campaign Review", format: "PDF", size: "1.8 MB", date: "Mar 31, 2026" },
];

export default function ReportsPage() {
  const [selectedTemplate, setSelectedTemplate] = useState(templates[0]);

  return (
    <AppShell>
      <div className="grid grid-cols-12 gap-6 h-full">
        <div className="col-span-7 space-y-6 overflow-y-auto">
          <div>
            <h1 className="text-xl font-semibold mb-1">Reporting Center</h1>
            <p className="text-sm text-[#64748B]">Generate executive reports, investor decks, and shareable dashboards.</p>
          </div>

          {/* Templates */}
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4">Report Templates</h2>
            <div className="space-y-2">
              {templates.map((t) => {
                const Icon = t.icon;
                return (
                  <button key={t.id} onClick={() => setSelectedTemplate(t)} className={cn("w-full card p-4 flex items-start gap-4 text-left transition-all", selectedTemplate.id === t.id && "border-[#A855F7]/50 bg-[#A855F7]/5")}>
                    <div className="w-9 h-9 rounded bg-[#1A1F2E] flex items-center justify-center shrink-0"><Icon className="w-4 h-4 text-[#94A3B8]" /></div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-medium">{t.name}</h3>
                        {t.starred && <Star className="w-3 h-3 text-amber-500 fill-amber-500" />}
                      </div>
                      <p className="text-xs text-[#64748B] mt-0.5">{t.desc}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Recent */}
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4">Recent Reports</h2>
            <div className="card overflow-hidden">
              {recentReports.map((r, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-3 border-b border-[#2A2F3A] last:border-0 hover:bg-[#1A1F2E] transition-colors cursor-pointer">
                  <div className="flex items-center gap-3">
                    <FileText className="w-4 h-4 text-[#64748B]" />
                    <div>
                      <p className="text-sm text-[#F8FAFC]">{r.name}</p>
                      <p className="text-[10px] font-mono text-[#64748B]">{r.format} · {r.size} · {r.date}</p>
                    </div>
                  </div>
                  <Download className="w-4 h-4 text-[#3A4150] hover:text-[#A855F7] transition-colors" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Preview */}
        <div className="col-span-5 space-y-4">
          <div className="card p-4 h-full flex flex-col">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-4">Preview: {selectedTemplate.name}</h3>
            <div className="flex-1 bg-[#05070D] rounded border border-[#2A2F3A] p-6 flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-lg bg-[#1A1F2E] flex items-center justify-center mb-4">
                <FileText className="w-8 h-8 text-[#3A4150]" />
              </div>
              <p className="text-sm text-[#94A3B8] mb-1">{selectedTemplate.name}</p>
              <p className="text-xs text-[#64748B] mb-6 max-w-xs">{selectedTemplate.desc}</p>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-xs text-[#64748B]"><Calendar className="w-3.5 h-3.5" /> Apr 1–30, 2026</div>
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button className="flex-1 py-2.5 bg-[#A855F7] text-white text-sm font-medium rounded hover:bg-[#9333EA] transition-colors">Generate PDF</button>
              <button className="flex-1 py-2.5 border border-[#2A2F3A] text-[#94A3B8] text-sm rounded hover:border-[#3A4150] hover:text-[#F8FAFC] transition-colors">Generate PPT</button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
