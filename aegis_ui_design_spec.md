# AEGIS UI/UX Design Specification (Refined)

**System Profile:** Decision Intelligence System
**Aesthetic:** High-Stakes Intelligence Command Center
**Core Principles:** Decisions First, Data Supports Decisions, Clarity Over Density, Strict Authoritative Tone.

---

## 1. UX Improvements & Missing Elements Addressed

### Integration of Missing Capabilities
1. **Focus Mode:** A global interaction state. Clicking any `Signal`, `Decision`, or `Chart Data Point` dims the rest of the application interface (`opacity-30`) and highlights all related nodes. For example, focusing a "Cost" signal highlights the Cost KPI, the Cost line on the chart, and filters the right panel Narration/Chat to cost-specific insights.
2. **Time Range Controls:** Placed directly in the global header (7D / 30D / 90D / Custom). Acts as a global pipeline filter. 
3. **Visual Confidence:** Confidence is no longer just text (`85%`). It is represented by a rigid, segmented bar meter (e.g., 10 discrete blocks). High confidence fills 8-10 blocks in green; moderate fills 5-7 in amber; low fills 1-4 in red.
4. **Chat-to-UI Linking:** Embedded citations within the Chatbot (`[Signal: Cost]`) trigger hover states that draw a literal glowing SVG connecting line or pulse effect on the corresponding KPI/Chart in the Main Content Pane.

### Cognitive Load & Decision Visibility
- **Priority Funneling:** The UI forces the user to look at the **Decision Header** first (top-left). If the state is `NO_SIGNAL` or `DATA_ISSUE`, the Chart Grid and KPIs desaturate slightly to imply "Do not over-analyze the noise."
- **Chart Usability:** Removed overlapping complex tooltips. Replaced with an active "Crosshair Tracker"—hovering over the chart syncs a vertical crosshair across *all* charts simultaneously, updating the KPI cards to show exact values at that specific timestamp.

---

## 2. Refined Layout Grid & Spacing System

### Spacing Scale (Tailwind mapping)
- **Micro:** `2px` (gap-0.5), `4px` (gap-1) — used inside dense signal chips and segmented meters.
- **Tight:** `8px` (gap-2), `12px` (gap-3) — internal component padding.
- **Base:** `16px` (gap-4) — standard section padding and card gaps.
- **Loose:** `24px` (gap-6), `32px` (gap-8) — major section separation.
- **Border Radius:** Sharp but modern. `2px` (rounded-sm) for inputs/buttons, `4px` (rounded) for main cards. Less rounded than before to increase the "technical/military" feel.

### Master Grid (Desktop - 1440px+)
- **Global Header (New):** Top bar containing App Title, Tenant, and **Time Range Controls**.
- **CSS Grid Base:** 12-column liquid layout.
- **Main Content Pane:** 9 columns (`col-span-9`).
- **Intelligence Panel:** 3 columns (`col-span-3`). Fixed height (`h-screen`) and sticky.
- **Gaps:** `24px` (`gap-6`) between panes. `16px` (`gap-4`) within grid rows.

---

## 3. Color System & Usage

**Palette Mapping:**
- **Background:** `#05070D` (Near-black)
- **Surface:** `#0E111A` (Dark slate)
- **Surface Hover/Focus:** `#1A1F2E`
- **Border/Divider:** `#2A2F3A`
- **Focus Mode Overlay:** `rgba(5, 7, 13, 0.7)` (70% opacity background mask)
- **Text Primary:** `#F8FAFC`
- **Text Secondary/Muted:** `#94A3B8`
- **Accent (Primary):** `#A855F7` (Deep violet) — Strictly for AI actions and Chat-to-UI linking highlights.
- **Status Warnings:** `#F59E0B` (Amber)
- **Status Success:** `#10B981` (Green)
- **Status Danger:** `#EF4444` (Red)

---

## 4. Refined UI Sections Breakdown

### Frame 1: Main Content Pane (Left, 75% width)

**A. Global Header Row**
- Left: System Name (AEGIS) & Tenant ID.
- Right: Technical segmented toggle for Time Range (`[ 7D | 30D | 90D | YTD ]`).

**B. Decision Header**
- **State Indicator:** Pill badge with status glow.
- **Headline:** Dominant H1 text.
- **Visual Confidence Meter:** 10-block segmented bar displaying structural certainty.

**C. KPI & Signal Row (Merged for Hierarchy)**
- Replaced the separate "Signal Strip". Signals are now fused with KPIs.
- 4-5 compact cards (`grid-cols-4` or `grid-cols-5`).
- Each card shows: Metric Name, Current Value, Delta, and a **Signal Chip** (if a signal exists for that metric) integrated directly below the value.

**D. Main Chart Grid**
- 2x2 grid. Minimalist. 
- Global Crosshair enabled: Hovering one chart shows data for that exact timestamp across all other charts and updates the KPI cards above temporarily.

**E. Tabbed Insight Panel**
- Flat, severe tabs (Decisions, Segments, Data Quality).
- *Signals tab removed* as signals are now contextualized within the KPIs and Decisions.
- Deep exploration tables that trigger **Focus Mode** when rows are clicked.

### Frame 2: Intelligence Panel (Right, 25% width, Fixed)

**A. Narration Terminal (Top)**
- Terminal-style briefing text.
- Metadata tags: `Mode: LLM | Grounded: True`.

**B. Chatbot Interface (Bottom)**
- Embedded citations `[1]`, `[2]`. Hovering a citation dims the rest of the app and draws an `#A855F7` glowing outline around the referenced KPI or Chart.

---

## 5. Updated Component Hierarchy (React Structure)

```jsx
<AegisCommandCenter>
  <GlobalHeader>
    <AppIdentity />
    <TimeRangeControls />
  </GlobalHeader>

  <MainWorkspace>
    <MainContentLayout className="col-span-9">
      
      <DecisionHeader>
        <StateIndicator state="ACTIONABLE" />
        <HeadlineText>Cost Efficiency Improving across Tier 1 Channels</HeadlineText>
        <VisualConfidenceMeter score={85} blocks={10} />
      </DecisionHeader>

      {/* KPIs and Signals fused for cognitive clarity */}
      <KpiSignalGrid>
        <KpiCard metric="Cost" value="$1.1M" delta="-12.5%">
          <SignalBadge direction="DOWN" type="BIAS" />
        </KpiCard>
        <KpiCard metric="Conversion" value="3.2%" delta="+0.4%">
          <SignalBadge direction="UP" type="DOMINANCE" />
        </KpiCard>
        <KpiCard metric="Revenue" value="$4.2M" delta="+5%" />
      </KpiSignalGrid>

      {/* Global crosshair provider wrapping the charts */}
      <CrosshairProvider>
        <ChartBentoGrid>
          <TrendChart metric="Cost" />
          <TrendChart metric="Conversion" />
          <TrendChart metric="Revenue" />
          <SegmentComparisonChart />
        </ChartBentoGrid>
      </CrosshairProvider>

      <DeepInsightTabs>
        <TabList>
          <Tab name="Decisions" active />
          <Tab name="Segments" />
          <Tab name="Data Quality" />
        </TabList>
        <TabPanel>
          <DecisionDataTable onRowClick={triggerFocusMode} />
        </TabPanel>
      </DeepInsightTabs>

    </MainContentLayout>

    <IntelligencePanel className="col-span-3">
      <NarrationTerminal text={narration} meta={narration_meta} />
      <ChatbotContext>
        <MessageList onCitationHover={triggerUIRoutingHighlight} />
        <CommandInput />
      </ChatbotContext>
    </IntelligencePanel>
  </MainWorkspace>
  
  {/* Absolute overlay for Focus Mode mask */}
  <FocusModeOverlay active={isFocusModeActive} />
</AegisCommandCenter>
```

---

## 6. Justification for Changes

1. **Integrating Signals into KPIs:** Previously, signals were in a separate strip, forcing the user's eyes to bounce between the KPI value ("Revenue is up") and the Signal Strip ("Is this an anomaly?"). Fusing them ensures immediate context. If a metric has a structural signal, it is flagged directly on the KPI card.
2. **Visual Confidence Meter:** A raw percentage (`85%`) requires cognitive processing. A 10-block segmented bar allows for instantaneous, peripheral understanding of system certainty, fitting the "intelligence dashboard" aesthetic.
3. **Crosshair Synchronization:** Instead of standalone tooltips, syncing the crosshair across all charts allows the user to easily visually correlate "When Cost dropped here, what happened to Revenue exactly at that moment?"
4. **Focus Mode (Dimming):** Dense UI can be overwhelming. By allowing the user to click a Decision and dimming everything unrelated, we drastically reduce cognitive load without removing the underlying depth of data.
5. **Chat-to-UI Highlighting:** Bridges the gap between the LLM and the deterministic UI. It proves to the user that the Chatbot is strictly grounded in the visible UI data, building trust in the system.

---

## 7. Tailwind-Style Class Suggestions (Refined)

**Visual Confidence Meter:**
```html
<div class="flex gap-1 items-center">
  <!-- Filled Block (High Confidence) -->
  <div class="w-2 h-4 bg-[#10B981] rounded-[1px] shadow-[0_0_4px_rgba(16,185,129,0.5)]"></div>
  <div class="w-2 h-4 bg-[#10B981] rounded-[1px]"></div>
  <!-- Empty Block -->
  <div class="w-2 h-4 bg-[#2A2F3A] rounded-[1px]"></div>
  <span class="ml-2 text-sm font-mono text-[#F8FAFC]">85%</span>
</div>
```

**Time Range Controls (Segmented Toggle):**
```html
<div class="flex p-1 bg-[#05070D] border border-[#2A2F3A] rounded">
  <button class="px-3 py-1 text-xs font-mono text-[#94A3B8] hover:text-[#F8FAFC]">7D</button>
  <button class="px-3 py-1 text-xs font-mono bg-[#2A2F3A] text-[#F8FAFC] rounded-sm">30D</button>
  <button class="px-3 py-1 text-xs font-mono text-[#94A3B8] hover:text-[#F8FAFC]">90D</button>
</div>
```

**Focus Mode Active State (on a specific Card):**
```html
<!-- When Focus mode is active, the focused card gets z-index elevation and a border glow -->
<div class="relative z-50 bg-[#0E111A] border border-[#A855F7] rounded-md p-4 shadow-[0_0_15px_rgba(168,85,247,0.15)]">
  <!-- Content -->
</div>
```

**Chatbot Citation:**
```html
<!-- Hovering triggers the highlight of the corresponding UI component -->
<span class="inline-flex items-center justify-center w-4 h-4 ml-1 text-[10px] font-mono border border-[#A855F7]/50 text-[#A855F7] rounded cursor-pointer hover:bg-[#A855F7] hover:text-white transition-colors">
  1
</span>
```
