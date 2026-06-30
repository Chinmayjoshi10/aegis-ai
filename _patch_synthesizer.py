"""Patch: replace STABLE padding block with signal-driven supporting decisions."""

path = r"c:\Users\chinm\aegis_ai\aegis_ai\company_brain\decision_synthesizer.py"

with open(path, "rb") as f:
    text = f.read().decode("utf-8").replace("\r\n", "\n")

OLD = """\
    # ── Pad to exactly 3 with stable-system fallbacks ───────────────────────
    # Suppress padding when at least one real decision already has substance
    _has_real_decision = any(
        d.get("type") not in ("STABLE", None)
        and (d.get("impact", 0) >= 0.3 or d.get("segments"))
        for d in result
    )
    if len(result) < _MAX_DECISIONS and not _has_real_decision:
        n_signals   = len(valid)
        avg_conf    = _avg_confidence(valid) if valid else 0.3
        avg_impact  = _compute_impact(valid) if valid else 0.15
        all_metrics = _extract_metrics(valid) if valid else []

        padding_pool = [
            {
                "type":       "STABLE",
                "title":      "System Baseline Is Stable",
                "summary":    (
                    f"Analysis of {n_signals} signal(s) across "
                    f"{len(all_metrics)} metric(s) found no critical anomalies. "
                    "The system is operating within expected parameters."
                ),
                "decision":   "No immediate action required. Continue monitoring.",
                "priority":   "LOW",
                "confidence": round(max(avg_conf, 0.30), 3),
                "impact":     round(max(avg_impact, 0.10), 3),
                "signals":    all_metrics[:3],
                "segments":   [],
                "visualization": {"chart": "summary", "x": "metric", "y": "confidence"},
            },
            {
                "type":       "STABLE",
                "title":      "Metrics Show Consistent Behaviour",
                "summary":    (
                    "Observed metrics are behaving consistently with historical patterns. "
                    "No structural shifts or concentration risks detected at this time."
                ),
                "decision":   "Maintain current strategy. Schedule a periodic review.",
                "priority":   "LOW",
                "confidence": round(max(avg_conf * 0.9, 0.25), 3),
                "impact":     round(max(avg_impact * 0.8, 0.08), 3),
                "signals":    all_metrics[3:6] if len(all_metrics) > 3 else all_metrics[:3],
                "segments":   [],
                "visualization": {"chart": "summary", "x": "metric", "y": "stability"},
            },
            {
                "type":       "STABLE",
                "title":      "No Critical Risks Detected",
                "summary":    (
                    "Risk assessment found no dominant concentrations or persistent drift "
                    "requiring immediate intervention. Monitoring is recommended."
                ),
                "decision":   "No critical risks at this time. Monitor key metrics weekly.",
                "priority":   "LOW",
                "confidence": round(max(avg_conf * 0.8, 0.20), 3),
                "impact":     round(max(avg_impact * 0.6, 0.06), 3),
                "signals":    all_metrics[:2] if all_metrics else ["system"],
                "segments":   [],
                "visualization": {"chart": "summary", "x": "metric", "y": "risk"},
            },
        ]

        used_titles = {d['title'] for d in result}
        for pad in padding_pool:
            if len(result) >= _MAX_DECISIONS:
                break
            if pad['title'] not in used_titles:
                result.append(pad)
                used_titles.add(pad['title'])

    return result"""

NEW = """\
    # ── Fill to 3 with signal-driven supporting decisions ───────────────────
    # Always runs when result < 3 — uses remaining valid events not already
    # covered. Never produces STABLE/generic text when real signals exist.
    if len(result) < _MAX_DECISIONS and valid:
        # Collect metrics already represented in result
        covered_metrics: set[str] = set()
        for d in result:
            for s in d.get("signals", []):
                covered_metrics.add(s.lower())

        # Sort remaining events by magnitude*confidence desc (deterministic)
        remaining = sorted(
            [e for e in valid if e.get("metric", "").lower() not in covered_metrics],
            key=lambda e: (
                -e.get("magnitude_pct", 0.0) * e.get("confidence", 0.0),
                e.get("metric", ""),
            ),
        )

        seen_support: set[str] = set()
        for ev in remaining:
            if len(result) >= _MAX_DECISIONS:
                break
            m = ev.get("metric", "")
            if not m or m.lower() in seen_support:
                continue
            seen_support.add(m.lower())
            result.append(_direct_event_decision(ev))

        # Context-alignment slot: if still short, describe signal agreement
        if len(result) < _MAX_DECISIONS and result:
            primary = result[0]
            p_signals = primary.get("signals", [])
            all_dirs = {e.get("direction") for e in valid}
            all_same_dir = len(all_dirs) == 1 and all_dirs != {""}
            ctx_summary = (
                f"All detected signals are aligned in the same direction, "
                f"reinforcing the primary finding in {', '.join(p_signals[:2])}. "
                "No conflicting trends detected across the monitored metrics."
            ) if all_same_dir else (
                f"Mixed directional signals detected across metrics. "
                f"The primary trend in {', '.join(p_signals[:2])} is accompanied by "
                "diverging movements in secondary metrics — investigate for structural causes."
            )
            segs, _ = _extract_segments(valid)
            result.append({
                "type":       "SIGNAL_CONTEXT",
                "title":      "Signal Alignment Across Metrics",
                "summary":    ctx_summary,
                "decision":   (
                    "Validate the primary trend against segment-level data. "
                    "Check whether the movement is concentrated or broad-based."
                ),
                "priority":   _priority(
                    primary.get("confidence", 0.3), primary.get("impact", 0.2)
                ),
                "confidence": round(primary.get("confidence", 0.3) * 0.85, 3),
                "impact":     round(primary.get("impact", 0.2) * 0.7, 3),
                "signals":    _extract_metrics(valid),
                "segments":   segs,
                "visualization": {"chart": "summary", "x": "metric", "y": "direction"},
            })

    return result"""

assert OLD in text, f"OLD block not found!\nLooking near: {text[text.find('Pad to exactly 3'):text.find('Pad to exactly 3')+200] if 'Pad to exactly 3' in text else 'NOT FOUND'}"

patched = text.replace(OLD, NEW, 1)
with open(path, "wb") as f:
    f.write(patched.replace("\n", "\r\n").encode("utf-8"))
print(f"PATCHED OK — {len(patched)} chars")
