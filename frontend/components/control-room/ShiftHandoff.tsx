"use client";

import { useEffect, useState } from "react";
import { Check, Clipboard, FileText, LoaderCircle, X } from "lucide-react";
import { api } from "../../lib/api";

export default function ShiftHandoff({ dataset, at }: { dataset: string; at: number }) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState<Awaited<ReturnType<typeof api.handoff>> | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [retry, setRetry] = useState(0);
  const [loadedKey, setLoadedKey] = useState("");
  const key = `${dataset}:${at}`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setError("");
    setBrief(null);
    setCopied(false);
    void api.handoff(dataset, at, controller.signal).then((value) => {
      if (!controller.signal.aborted) { setBrief(value); setLoadedKey(key); }
    }).catch((e: Error) => {
      if (!controller.signal.aborted) setError(e.message);
    });
    return () => controller.abort();
  }, [open, dataset, at, key, retry]);
  const current = loadedKey === key ? brief : null;
  const stamp = new Date(at * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC";
  async function copy() {
    if (!current) return;
    try {
      await navigator.clipboard.writeText(`NightShift AI · Shift handoff\n${stamp}\n${dataset}\n\n${current.summary.join("\n\n")}\n\nRecommendations only; no actions dispatched.`);
      setCopied(true);
    } catch { setError("Clipboard unavailable. Select and copy the brief text below."); }
  }
  return (
    <details className="shift-handoff" onToggle={(event) => setOpen(event.currentTarget.open)}
      onKeyDown={(event) => { if (event.key === "Escape") event.currentTarget.open = false; }}>
      <summary><FileText size={14} />Shift handoff<span>30-sec brief</span></summary>
      <section aria-label="Shift handoff brief" className="handoff-popover">
        <header><div><strong>For the next operator</strong><time dateTime={new Date(at * 1000).toISOString()}>{stamp}</time></div>
          <div style={{ display: "flex" }}><button className="icon-button" onClick={() => void copy()} disabled={!current} aria-label="Copy shift handoff">{copied ? <Check size={16} /> : <Clipboard size={16} />}</button>
            <button className="icon-button" aria-label="Close shift handoff" onClick={(event) => { const details = event.currentTarget.closest("details"); if (details) details.open = false; }}><X size={16}/></button></div>
        </header>
        {error && <p role="alert">{error} {!current && <button className="ui-button" onClick={() => setRetry(n => n + 1)}>Retry</button>}</p>}
        {!current && !error && <p role="status"><LoaderCircle size={14} className="spin" /> Preparing recorded shift brief…</p>}
        {current && <div className="handoff-lines">{current.summary.map((line, i) => <p key={i}>{line}</p>)}</div>}
        <footer>Recorded telemetry · Recommendations only; no actions dispatched.</footer>
      </section>
    </details>
  );
}
