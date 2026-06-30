"use client";

import { useState, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { useAnalysis } from "@/hooks/useAnalysis";
import { Upload, CheckCircle, AlertCircle, Loader2, X } from "lucide-react";

export function UploadWorkflow({ onComplete }: { onComplete?: () => void }) {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState("general");
  const [complete, setComplete] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { runAnalysis, isLoading, error, uploadProgress, uploadStage } = useAnalysis();

  const handleFile = useCallback((f: File) => {
    const validTypes = [".csv", ".xlsx", ".json"];
    const ext = f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
    if (!validTypes.includes(ext)) return;
    setFile(f);
    setComplete(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
  }, [handleFile]);

  const handleSubmit = useCallback(async () => {
    if (!file) return;
    try {
      await runAnalysis(file, domain);
      setComplete(true);
      onComplete?.();
    } catch {
      // Error is already in store
    }
  }, [file, domain, runAnalysis, onComplete]);

  if (isLoading) {
    return (
      <div className="card p-8 text-center">
        <Loader2 className="w-10 h-10 text-[#A855F7] mx-auto mb-4 animate-spin" />
        <h3 className="text-sm font-medium text-[#F8FAFC] mb-2">{uploadStage}</h3>
        <div className="w-full max-w-xs mx-auto h-2 bg-[#1A1F2E] rounded-full overflow-hidden mb-2">
          <div
            className="h-full bg-[#A855F7] rounded-full transition-all duration-500"
            style={{ width: `${uploadProgress}%` }}
          />
        </div>
        <p className="text-[10px] font-mono text-[#64748B]">{uploadProgress}% complete</p>

        {/* Stage Pipeline */}
        <div className="mt-6 grid grid-cols-5 gap-2 max-w-md mx-auto">
          {["Profile", "Map", "Baseline", "Signals", "Bias", "Confidence", "Cross-val", "Decisions", "Narrate"].map((s, i) => {
            const stageProgress = (uploadProgress / 100) * 9;
            const done = i < stageProgress;
            const active = i >= stageProgress && i < stageProgress + 1;
            return (
              <div key={s} className="text-center">
                <div className={cn("w-6 h-6 rounded-full mx-auto mb-1 flex items-center justify-center text-[8px] font-mono transition-all",
                  done ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" :
                  active ? "bg-[#A855F7]/20 text-[#A855F7] border border-[#A855F7]/30 animate-pulse" :
                  "bg-[#1A1F2E] text-[#334155] border border-[#2A2F3A]"
                )}>
                  {done ? "✓" : i + 1}
                </div>
                <span className={cn("text-[8px] font-mono", done ? "text-emerald-400" : active ? "text-[#A855F7]" : "text-[#334155]")}>{s}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (complete) {
    return (
      <div className="card p-8 text-center">
        <CheckCircle className="w-10 h-10 text-emerald-500 mx-auto mb-4" />
        <h3 className="text-sm font-medium text-[#F8FAFC] mb-1">Analysis Complete</h3>
        <p className="text-xs text-[#64748B] mb-4">Your data has been processed through the AEGIS intelligence pipeline.</p>
        <button onClick={() => { setFile(null); setComplete(false); }} className="px-4 py-2 text-xs border border-[#2A2F3A] rounded text-[#94A3B8] hover:border-[#3A4150] transition-colors">
          Upload Another
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={cn(
          "card border-dashed border-2 p-12 text-center cursor-pointer transition-all",
          dragOver ? "border-[#A855F7]/50 bg-[#A855F7]/5" : "border-[#2A2F3A] hover:border-[#3A4150]"
        )}
      >
        <Upload className={cn("w-10 h-10 mx-auto mb-4 transition-colors", dragOver ? "text-[#A855F7]" : "text-[#3A4150]")} />
        <p className="text-sm text-[#94A3B8] mb-1">Drop CSV or Excel file here</p>
        <p className="text-[11px] text-[#64748B] font-mono">Supported: .csv .xlsx .json · Max 500MB</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.json"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
      </div>

      {/* File selected */}
      {file && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-[#A855F7]/10 flex items-center justify-center">
                <Upload className="w-4 h-4 text-[#A855F7]" />
              </div>
              <div>
                <p className="text-sm text-[#F8FAFC]">{file.name}</p>
                <p className="text-[10px] font-mono text-[#64748B]">{(file.size / 1024).toFixed(0)} KB</p>
              </div>
            </div>
            <button onClick={() => setFile(null)} className="p-1 text-[#3A4150] hover:text-[#94A3B8]">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label className="text-[10px] font-mono text-[#64748B] uppercase mb-1 block">Domain</label>
              <select
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                className="w-full bg-[#05070D] border border-[#2A2F3A] rounded px-3 py-2 text-xs text-[#F8FAFC] outline-none focus:border-[#A855F7]"
              >
                <option value="general">General</option>
                <option value="marketing">Marketing</option>
                <option value="sales">Sales</option>
                <option value="operations">Operations</option>
                <option value="supply_chain">Supply Chain</option>
                <option value="finance">Finance</option>
              </select>
            </div>
            <button
              onClick={handleSubmit}
              className="px-6 py-2.5 bg-[#A855F7] text-white text-sm font-medium rounded hover:bg-[#9333EA] transition-all hover:shadow-[0_0_20px_rgba(168,85,247,0.3)] mt-4"
            >
              Analyze
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card p-4 border-red-500/30 bg-red-500/5">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <p className="text-xs text-red-400">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
