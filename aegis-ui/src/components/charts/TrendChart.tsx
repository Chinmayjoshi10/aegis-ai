"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

interface TrendChartProps {
  title: string;
  data: Record<string, unknown>[];
  dataKey: string;
  color?: string;
  formatValue?: (v: number) => string;
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#1E2433] border border-[#3A4150] rounded px-3 py-2 text-xs">
      <p className="text-[#64748B] font-mono">{label}</p>
      <p className="text-[#F8FAFC] font-mono font-medium">{typeof payload[0].value === "number" ? payload[0].value.toLocaleString() : payload[0].value}</p>
    </div>
  );
}

export function TrendChart({ title, data, dataKey, color = "#F8FAFC" }: TrendChartProps) {
  return (
    <div className="card p-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#94A3B8] mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} syncId="aegis-global-charts">
          <CartesianGrid strokeDasharray="3 3" stroke="#1A1F2E" />
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#64748B" }} tickLine={false} axisLine={{ stroke: "#2A2F3A" }} interval={4} />
          <YAxis tick={{ fontSize: 10, fill: "#64748B" }} tickLine={false} axisLine={false} width={50} />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#A855F7", strokeWidth: 1 }} />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5} dot={false} activeDot={{ r: 4, fill: color, stroke: "#0E111A", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
