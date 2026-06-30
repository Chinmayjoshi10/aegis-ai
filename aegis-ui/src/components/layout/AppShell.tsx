"use client";

import { Sidebar } from "./Sidebar";
import { GlobalHeader } from "./GlobalHeader";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-screen flex overflow-hidden bg-[#020409]">
      <Sidebar />
      <div className="flex-1 flex flex-col ml-16">
        <GlobalHeader />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
