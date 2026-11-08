import {
  ArrowLeft,
  Download,
  RotateCcw,
  Waves,
} from "lucide-react";
import type { Dashboard, Navigation } from "../../lib/types";
import type { Operator } from "../../lib/operators";
import { useState } from "react";
import { timestamp } from "../../lib/operational-status";

export default function TopBar({
  datasets,
  dataset,
  data,
  navigation,
  busy,
  onDataset,
  onNavigate,
  onReset,
  onBack,
  people,
  assignments,
}: {
  datasets: string[];
  dataset: string;
  data: Dashboard | null;
  navigation: Navigation;
  busy: boolean;
  onDataset: (name: string) => void;
  onNavigate: (nav: Navigation) => void;
  onReset: () => void;
  onBack: () => void;
  people: Operator[];
  assignments: Record<string, number>;
}) {
  // assignments maps system -> operator, so viewing by operator needs the
  // reverse lookup. Operator 1 covers the first system, 2 the second, and so on.
  const systemForOperator: Record<number, string> = {};
  for (const [systemId, operatorId] of Object.entries(assignments)) {
    systemForOperator[operatorId] = systemId;
  }
  const [notice, setNotice] = useState("");
  function exportSnapshot() {
    if (!data) return;
    const blob = new Blob([JSON.stringify({ dataset, now: data.now, events: data.alerts, source: "Currently loaded recorded telemetry" }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const download = document.createElement("a");
    download.href = url;
    download.download = "nightshift-events.json";
    download.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice("Exported the currently loaded incidents. No backend connection needed.");
    window.setTimeout(() => setNotice(""), 4000);
  }
  return (
    <header className="topbar" data-view={navigation.facilityId ? 'facility' : navigation.systemId ? 'system' : 'network'}>
      <button type="button" onClick={() => onNavigate({})} className="brand" title="Return to all systems" style={{ background: "none", border: 0, padding: 0, textAlign: "left" }}>
        <span className="brand-symbol">
          <Waves size={22} />
        </span>
        <span>
          NightShift <em>AI</em>
        </span>
      </button>
      <label className="operator-control"><span className="view-caption">Operator</span>
        <select
          aria-label="View the system assigned to an operator"
          disabled={!data}
          value={navigation.systemId ? assignments[navigation.systemId] ?? "" : ""}
          onChange={(e) => {
            const id = Number(e.target.value);
            // Clearing the operator widens the view back to the whole field.
            onNavigate(
              e.target.value && systemForOperator[id]
                ? { systemId: systemForOperator[id] }
                : {},
            );
          }}
        >
          <option value="">All operators</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              #{person.id} {person.name} · System {systemForOperator[person.id] ?? "—"}
            </option>
          ))}
        </select>
      </label>
      <label className="system-control"><span className="view-caption">3D view</span>
        <select aria-label="Navigate to system" value={navigation.systemId || ''} disabled={!data} onChange={e => onNavigate(e.target.value ? { systemId: e.target.value } : {})}>
          <option value="">All systems</option>{data?.systems.map(system => <option key={system.id} value={system.id}>System {system.id}</option>)}
        </select>
      </label>
      <label className="dataset-control">
        <span className="dataset-caption">Dataset</span>
        <select
          value={dataset}
          aria-label="Select telemetry dataset"
          title={dataset}
          onChange={(e) => onDataset(e.target.value)}
          disabled={!datasets.length}
        >
          {!datasets.length && <option>Connecting…</option>}
          {datasets.map((d) => (
            <option value={d} key={d}>
              {d.replace("history/", "").replace("snapshot_", "Snapshot · ").replace("mock_test_", "Mock · ").replace("full_week", "Full week recording").replace("T", " / ")}
            </option>
          ))}
        </select>
      </label>
      <div className="replay-status">
        <span>
          <i />
          {busy ? "Loading recording" : "Recorded telemetry"}
        </span>
        <time>{data ? timestamp(data.now).replace(",", ` ${new Date(data.now * 1000).getUTCFullYear()} \u00b7`) : "Awaiting dataset"}</time>
      </div>
      <div className="toolbar-actions">
        <button className="icon-button" onClick={onBack} disabled={!navigation.systemId} title="Back one navigation level" aria-label="Back one navigation level"><ArrowLeft size={17}/></button>
        {data && (
          <button
            className="icon-button export-button"
            onClick={exportSnapshot}
            title="Export current incidents"
            aria-label="Export current incidents"
          >
            <Download size={16} />
          </button>
        )}
        <button
          className="icon-button"
          onClick={onReset}
          disabled={!data}
          title="Reset current camera"
          aria-label="Reset current view"
        >
          <RotateCcw size={16} />
        </button>
      </div>
      {notice && <div role="status" className="toolbar-notice">{notice}</div>}
    </header>
  );
}
