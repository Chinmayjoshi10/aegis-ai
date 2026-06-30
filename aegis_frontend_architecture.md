# AEGIS Frontend Architecture

## 1. Overview
The AEGIS Decision Intelligence System is designed as a high-stakes command center. The frontend architecture reflects this seriousness by prioritizing data density, visual strictness, and complex interactivity. Built on React (Next.js) with Tailwind CSS, the system leverages a deterministic UI foundation heavily augmented by real-time LLM narration and localized contextual highlighting (Focus Mode & Chat-to-UI linking).

This document serves as the implementation blueprint, converting the UX/UI specification into developer-ready code structures, state management patterns, and interactive systems.

---

## 2. Folder Structure
The architecture follows a feature-based structure to accommodate high complexity, ensuring strict separation between raw UI components, interactive contexts, and data integrations.

```text
/src
  /app                       # Next.js App Router
    layout.tsx               # Global wrapper, body styles
    page.tsx                 # Main command center entry point
  /components
    /layout
      GlobalHeader.tsx       # System Identity, Mode, Data Context
      MainWorkspace.tsx      # Main layout grid container
    /decisions
      DecisionHeader.tsx     # State, Headline, Visual Confidence
      DecisionDataTable.tsx  # Deep exploration
    /kpi
      KpiSignalGrid.tsx      # Fused KPIs and Signals container
      KpiCard.tsx            # Individual metric card
      SignalBadge.tsx        # Integrated signal direction/type
    /charts
      ChartBentoGrid.tsx     # Bento layout wrapper
      TrendChart.tsx         # Recharts implementation
      SegmentComparison.tsx  # Granular data
    /intelligence
      IntelligencePanel.tsx  # Right pane wrapper
      NarrationTerminal.tsx  # Typewriter effect LLM briefing
      ChatbotContext.tsx     # Chat interface and citations
    /ui                      # Shared primitives
      VisualConfidence.tsx   # 10-block segmented meter
      FocusModeOverlay.tsx   # Global dimming mask
      LoadingScanner.tsx     # Radar/scanning load effect
  /context
    FocusModeContext.tsx     # Global focus state
    CrosshairContext.tsx     # Synchronized chart scrubbing
    TimeRangeContext.tsx     # Global data filters
  /hooks
    useAegisData.ts          # Core API data fetching
    useTypewriter.ts         # Narration streaming effect
  /store
    aegisStore.ts            # Zustand global state (if needed over Context)
  /lib
    utils.ts                 # Tailwind merge, formatting
```

---

## 3. Component Architecture

### Layout Components
- **`GlobalHeader`**: Houses App Identity, `TimeRangeControls`, `SystemModeIndicator` (DETERMINISTIC vs LLM AUGMENTED), and `DataContext` (Last Updated, Data Window).
- **`MainWorkspace`**: Sets the strict 12-column grid (`col-span-9` for main content, `col-span-3` for the fixed right panel).

### Feature Components
- **Decision Engine**: `DecisionHeader` leads the visual hierarchy. If `NO_SIGNAL` or `DATA_ISSUE`, child components (Charts, KPIs) consume this state to desaturate themselves. Decision cards enforce **Priority Visuals**: CRITICAL (red border, stark weight), HIGH (amber), MEDIUM (subtle).
- **Analytics Engine**: `KpiSignalGrid` and `ChartBentoGrid` display raw data infused with signal overlays.
- **Intelligence Engine**: `NarrationTerminal` and `ChatbotContext` handle LLM outputs, including the critical citation hover logic that links back to the Analytics components.

---

## 4. Core Providers

Complex interactions require global coordination. We use React Context (or Zustand slices) to prevent prop drilling.

1. **`FocusModeProvider`**
   - *Responsibility*: Tracks if Focus Mode is active and which `entity_id` (e.g., `signal_cost_123`) is currently focused.
   - *Behavior*: Injects an `isFocused` and `isDimmed` boolean into every major UI card. Unfocused cards drop to `opacity-30`.

2. **`CrosshairProvider`**
   - *Responsibility*: Holds the currently hovered timestamp/X-axis index across all charts.
   - *Behavior*: Ensures that hovering over the Revenue chart immediately renders the vertical crosshair line and active dot on the Cost and Conversion charts simultaneously.

3. **`TimeRangeProvider`**
   - *Responsibility*: Manages global data filtering parameters (7D, 30D, 90D). Triggers data re-fetching when toggled.

---

## 5. Implementation Details

### Loading & Empty States
- **Loading State**: Uses a CSS-animated `LoadingScanner` (a sweeping radar line across a wireframe layout) while `useAegisData` resolves.
- **Empty States (`NO_SIGNAL` / `DATA_ISSUE`)**: The `DecisionHeader` explicitly declares the state. The `KpiSignalGrid` and `ChartBentoGrid` read this state, applying a `grayscale opacity-50` class to reduce visual noise, ensuring the user focuses solely on the system message.

### Performance Strategy
- **Memoization**: Heavy charting components (`TrendChart`) must be wrapped in `React.memo` to prevent re-renders when the Chatbot types out text.
- **Virtualization**: `DecisionDataTable` must use `@tanstack/react-virtual` to handle hundreds of segment rows without dropping frames.
- **Event Throttling**: The `CrosshairProvider` state updates (which trigger every pixel of mouse movement on a chart) must be heavily throttled or handled via Recharts' native `syncId` to avoid React render cycle bottlenecks.

---

## 6. Sample Code

### 6.1. Global Header (System Mode & Data Context)
```tsx
export function GlobalHeader() {
  return (
    <header className="flex items-center justify-between px-6 py-3 bg-[#05070D] border-b border-[#2A2F3A]">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-widest text-[#F8FAFC]">AEGIS</h1>
        <div className="px-2 py-0.5 text-[10px] border border-[#A855F7]/30 text-[#A855F7] bg-[#A855F7]/10 rounded font-mono">
          SYSTEM MODE: LLM AUGMENTED
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="text-[10px] font-mono text-[#94A3B8] text-right">
          <p>Last Updated: 2 mins ago</p>
          <p>Data Window: 30 Days</p>
        </div>
        <TimeRangeControls />
      </div>
    </header>
  );
}
```

### 6.2. Visual Confidence Meter
```tsx
export function VisualConfidence({ score }: { score: number }) {
  // Score is 0-100. Calculate filled blocks out of 10.
  const filledBlocks = Math.round(score / 10);
  const color = score >= 80 ? 'bg-[#10B981]' : score >= 50 ? 'bg-[#F59E0B]' : 'bg-[#EF4444]';
  const glow = score >= 80 ? 'shadow-[0_0_6px_rgba(16,185,129,0.4)]' : '';

  return (
    <div className="flex gap-1 items-center">
      {Array.from({ length: 10 }).map((_, i) => (
        <div 
          key={i} 
          className={`w-2 h-4 rounded-[1px] ${i < filledBlocks ? `${color} ${glow}` : 'bg-[#2A2F3A]'}`}
        />
      ))}
      <span className="ml-2 text-sm font-mono text-[#F8FAFC]">{score}%</span>
    </div>
  );
}
```

### 6.3. Fused KPI & Signal Card (With Focus Mode)
```tsx
export function KpiCard({ metric, value, delta, signal, id }) {
  const { isFocused, activeId, setFocus } = useFocusMode();
  const dimmed = activeId !== null && activeId !== id;

  return (
    <div 
      onClick={() => setFocus(activeId === id ? null : id)}
      className={`
        bg-[#0E111A] border border-[#2A2F3A] rounded-md p-4 flex flex-col transition-all cursor-pointer
        ${dimmed ? 'opacity-30 grayscale' : 'opacity-100'}
        ${isFocused(id) ? 'border-[#A855F7] shadow-[0_0_15px_rgba(168,85,247,0.15)] z-50 relative' : ''}
      `}
    >
      <span className="text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">{metric}</span>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-2xl font-medium tabular-nums">{value}</span>
        <span className="text-xs text-[#10B981] tabular-nums">{delta}</span>
      </div>
      
      {/* Integrated Signal Badge */}
      {signal && (
        <div className="mt-3 pt-3 border-t border-[#2A2F3A]">
          <SignalBadge direction={signal.direction} type={signal.type} />
        </div>
      )}
    </div>
  );
}
```

### 6.4. Chat-to-UI Citation Link
```tsx
export function ChatCitation({ id, label }) {
  const { setFocus } = useFocusMode();
  
  return (
    <span 
      onMouseEnter={() => setFocus(id)}
      onMouseLeave={() => setFocus(null)}
      className="inline-flex items-center justify-center px-1.5 py-0.5 ml-1 text-[10px] font-mono border border-[#A855F7]/50 text-[#A855F7] rounded cursor-pointer hover:bg-[#A855F7] hover:text-white transition-colors"
    >
      {label}
    </span>
  );
}
```

---

## 7. Interaction Systems

### Focus Mode (Global Dimming & Highlighting)
When a user clicks a Decision or hovers a Chat Citation, `FocusModeContext` updates `activeId`. 
An absolutely positioned `<FocusModeOverlay />` activates, rendering a fixed `bg-[#05070D]/70` block over the screen (`z-40`). 
Components matching `activeId` dynamically apply `z-50 relative` to lift themselves above the overlay, creating a striking "spotlight" effect.

### Crosshair Sync (Recharts)
Instead of managing complex manual mouse tracking, utilize Recharts' native `syncId` prop.
```tsx
<ResponsiveContainer width="100%" height={200}>
  <LineChart data={data} syncId="aegis-global-charts">
    <Tooltip cursor={{ stroke: '#A855F7', strokeWidth: 1 }} content={<CustomTooltip />} />
    <Line type="monotone" dataKey="value" stroke="#F8FAFC" strokeWidth={1.5} dot={false} />
  </LineChart>
</ResponsiveContainer>
```
When multiple charts share `syncId="aegis-global-charts"`, Recharts automatically syncs the active tooltip and vertical crosshair line across all mounted instances.

---

## 8. State Management Strategy

We recommend **Zustand** for global state (Focus Mode, Crosshair data, UI Settings) because:
1. It avoids the React Context re-render hell (components only re-render if the specific slice of state they subscribe to changes).
2. It allows state updates outside of the React render cycle (crucial for high-performance chart scrubbing).

React Context should only be used for deeply embedded UI themes or static configuration data that rarely changes.

### Loading / Processing Execution Flow
1. User requests data → App mounts `MainWorkspace`.
2. `useAegisData` resolves → Shows `<LoadingScanner />`.
3. Data arrives → KPI, Charts, and Decisions populate instantly.
4. `useTypewriter` hook fires → `NarrationTerminal` streams the text character-by-character at ~30ms intervals, giving the system a "live analysis" feel.
