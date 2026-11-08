"use client";
import { useEffect, useState } from "react";
import { ChevronRight, Crosshair, Gauge, ShieldCheck, X, Activity, Clock3, ArrowRight, ArrowLeft } from "lucide-react";
import type { Asset, Dashboard, Selection, TrendPoint } from "../../lib/types";
import { api } from "../../lib/api";
import {
  equipmentState,
  formatValue,
  humanize,
  metricInfo,
  money,
} from "../../lib/operational-status";
import SensorTrend from "../charts/SensorTrend";
import NemotronInvestigation from "./NemotronInvestigation";

export default function AssetInspector({
  asset,
  selection,
  data,
  dataset,
  disabled,
  onClose,
  onFocus,
  onSelect,
  expanded,
  onExpandedChange,
}: {
  asset: Asset;
  selection: Selection;
  data: Dashboard;
  dataset: string;
  disabled: boolean;
  onClose: () => void;
  onFocus: () => void;
  onSelect: (s: Selection) => void;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const facility = data.facilities.find((f) => f.id === asset.facilityId);
  const incident = data.alerts.find((a) => a.facility_id === asset.facilityId);
  const state = equipmentState(asset, facility, incident, data.limits);
  const [readings, setReadings] = useState<Record<string, TrendPoint[]>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const metric =
    selection.metric && asset.metrics.includes(selection.metric)
      ? selection.metric
      : asset.metrics[0];
  const metricsKey = asset.metrics.join(",");
  useEffect(() => {
    const controller = new AbortController();
    setReadings({});
    setErrors({});
    const metrics = metricsKey ? metricsKey.split(",") : [];
    setLoading(metrics.length > 0);
    void Promise.all(
      metrics.map(async (name) => {
        try {
          const points = await api.trend(
            dataset,
            asset.id,
            name,
            data.now,
            controller.signal,
          );
          if (!controller.signal.aborted)
            setReadings((prev) => ({ ...prev, [name]: points }));
        } catch (e) {
          if (!controller.signal.aborted)
            setErrors((prev) => ({ ...prev, [name]: (e as Error).message }));
        }
      }),
    ).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [dataset, asset.id, data.now, metricsKey]);
  const friendlyName = asset.kind === 'disposal' ? 'Disposal site' : asset.kind === 'yard' ? 'Truck yard' : asset.id.replace(/^.*_(WELL|TANK|PUMP|PIPELINE)_/, (_, kind: string) => kind.charAt(0) + kind.slice(1).toLowerCase() + ' ');
  const plan = incident?.recommendation;
  const well = facility?.wells.find((w) => w.id === asset.id);
  const disposal = data.systems.find(
    (s) => s.disposal_site.id === asset.id,
  )?.disposal_site;
  return (
    <aside
      className={"asset-inspector " + (expanded ? "details-open" : "summary-only")}
      aria-label={`${asset.id} inspector`}
    >
      <div className="inspector-heading">
        <button className="inspector-back" onClick={() => onExpandedChange(false)}><ArrowLeft size={15}/>Asset details</button>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close asset inspector"
        >
          <X size={17} />
        </button>
      </div>
      {!expanded && <div className="asset-summary">
        <div className="summary-heading">
          {asset.kind === 'pump' ? <svg className="pump-icon" width="31" height="31" viewBox="0 0 32 32" fill="none" stroke={state.color} strokeWidth="1.6" aria-hidden="true"><circle cx="10" cy="17" r="5"/><rect x="15" y="12" width="10" height="10" rx="2"/><path d="M4 26h25M7 22v4m15-4v4M6 13V6h7v5m12 6h4V9h-4M18 12v10m3-10v10"/></svg> : <Activity size={29} style={{ color: state.color }}/>}
          <div><h2>{friendlyName}</h2><p>{facility ? facility.id.replace(/^.*_FACILITY_/, 'Facility ') + ' · ' : ''}System {asset.systemId}</p></div>
          <span className="state-pill" style={{ color: state.color, borderColor: state.color + '55' }}>{state.label === "Pump fault" ? "Fault detected" : state.label}</span>
          <button className="summary-close icon-button" onClick={onClose} aria-label="Close asset summary"><X size={15}/></button>
        </div>
        <dl className="summary-evidence">
          {incident && <div><dt><Clock3 size={16}/>Incident began</dt><dd><time dateTime={new Date(incident.onset_unix * 1000).toISOString()}>{new Date(incident.onset_unix * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC", hour12: false })} UTC</time><br/><span>{Math.max(0, Math.floor((data.now - incident.onset_unix) / 3600))}h {Math.max(0, Math.floor((data.now - incident.onset_unix) / 60) % 60)}m elapsed</span></dd></div>}
          <div><dt><Activity size={16}/>Evidence</dt><dd>{asset.kind === 'pump' && facility ? `${state.label} · Output ${formatValue(facility.flow_bpd)} bbl/day` : incident?.evidence[0] || state.label}</dd></div>
          <div><dt><Clock3 size={16}/>{incident?.category === 'pump_failure' ? 'Shutdown risk' : 'Assessment'}</dt><dd className={incident ? 'exception-value' : ''} style={incident?.category === 'pump_degradation' ? { color: state.color } : undefined}>{incident?.category === 'pump_failure' && incident.hours_to_limit != null ? `${incident.hours_to_limit.toFixed(1)}h to shutdown` : incident ? 'Inspection required' : 'No active incident'}</dd></div>
        </dl>
        <button className="inspect-response" onClick={() => onExpandedChange(true)}>Inspect response<ArrowRight size={19}/></button>
      </div>}
      <div className="inspector-scroll">
        <div className="asset-title">
          <span className="asset-type">
            {asset.kind === "yard"
              ? "TRUCK YARD"
              : asset.kind === "disposal"
                ? "DISPOSAL SITE"
                : asset.kind.toUpperCase()}
          </span>
          <h1>{friendlyName}</h1><code className="exact-asset-id">{asset.id}</code>
          <p>
            <i style={{ background: state.color }} />
            {state.label}
          </p>
        </div>
        <button className="focus-button" onClick={onFocus} disabled={disabled}>
          <Crosshair size={14} />
          Focus equipment
          <ChevronRight size={13} />
        </button>
        {asset.metrics.length > 0 && (
          <section className="inspector-section">
            <div className="section-heading">
              <Gauge size={14} />
              <h2>Recorded measurements</h2>
            </div>
            <div className="measurement-list">
              {asset.metrics.map((name) => {
                const points = readings[name];
                const value = points?.[points.length - 1]?.value;
                const status =
                  name === "status" && value != null
                    ? asset.kind === "pump"
                      ? (
                          { 0: "Stopped", 1: "Running", 2: "Fault" } as Record<
                            number,
                            string
                          >
                        )[value]
                      : (
                          { 0: "Shut in", 1: "Producing" } as Record<
                            number,
                            string
                          >
                        )[value]
                    : null;
                return (
                  <button
                    key={name}
                    disabled={disabled}
                    className={metric === name ? "selected" : ""}
                    onClick={() =>
                      onSelect({ assetId: asset.id, metric: name })
                    }
                  >
                    <span>{metricInfo[name]?.label || name}</span>
                    <b>
                      {value == null
                        ? loading
                          ? "Loading…"
                          : "Unavailable"
                        : status || formatValue(value)}
                      <small>
                        {value != null && !status ? metricInfo[name]?.unit : ""}
                      </small>
                    </b>
                  </button>
                );
              })}
            </div>

          </section>
        )}
        {asset.kind === "tank" && facility && (
          <div className="spec-list">
            <span>
              Configured capacity{" "}
              <b>{formatValue(facility.tank.capacity_bbl, 0)} bbl</b>
            </span>
            <span>
              Warning / shutdown{" "}
              <b>
                {data.limits.warning}% / {data.limits.shutdown}%
              </b>
            </span>
          </div>
        )}
        {well && (
          <div className="spec-list">
            <span>
              Catalog oil production{" "}
              <b>{formatValue(well.oil_bpd, 0)} bbl/day</b>
            </span>
            <span>
              Catalog gas production{" "}
              <b>{formatValue(well.gas_mcfd, 0)} mcf/day</b>
            </span>
            <p className="fine-print">
              Configured production rates; these are not live oil/gas sensors.
            </p>
          </div>
        )}
        {disposal && (
          <section className="inspector-section">
            <h2>Shared disposal destination</h2>
            <p>
              Facility pipelines in system {asset.systemId} connect to this
              installation.
            </p>
            <div className="spec-list">
              <span>
                Configured pressure{" "}
                <b>{formatValue(disposal.pressure_psi, 0)} psi</b>
              </span>
            </div>
            <p className="fine-print">
              The dataset provides no disposal-site sensors. This is a network
              configuration value.
            </p>
          </section>
        )}
        {asset.kind === "yard" && (
          <section className="inspector-section">
            <h2>Fleet resource area</h2>
            <p>
              The tanker is a symbolic representation, not a truck count or
              dispatch. The current API does not expose fleet size, live
              availability, truck identities or movement.
            </p>
            <p className="fine-print">
              Truck recommendations are visible in the affected facility’s
              response panel. No trucks have been dispatched by this interface.
            </p>
          </section>
        )}
        {incident && (
          <section className="inspector-section incident-evidence">
            <div className="section-heading">
              <span
                className={
                  "status-dot " +
                  (incident.category === "pump_degradation"
                    ? "warning"
                    : "fault")
                }
              />
              <h2>{humanize(incident.category)}</h2>
              <span className="context-label">FACILITY CONTEXT</span>
            </div>
            {incident.category === "pump_failure" &&
              incident.hours_to_limit != null && (
                <div className="countdown">
                  <strong>
                    {incident.hours_to_limit.toFixed(2)}
                    <small>h</small>
                  </strong>
                  <span>
                    until automatic shutdown
                    <br />
                    <small>Backend estimate · no intervention</small>
                  </span>
                </div>
              )}
            {incident.category === "pipeline_leak" && (
              <p className="fine-print">
                The fault is associated with {facility?.pipeline.id}; the
                dataset does not locate the leak along the pipe.
              </p>
            )}
            <ul className="evidence-list">
              {incident.evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
            <p className="fine-print">
              Evidence confidence {(incident.confidence * 100).toFixed(1)}% · not a calibrated probability
              {incident.confidence_basis && <><br/>{incident.confidence_basis.method} · {incident.confidence_basis.samples} recorded readings at this replay time.</>}
            </p>
          </section>
        )}
        {plan && (
          <section className="inspector-section response-section">
            <div className="section-heading">
              <ShieldCheck size={14} />
              <h2>
                {plan.verified
                  ? "Verified response candidate"
                  : "Recommended response"}
              </h2>
            </div>
            <h3>{plan.label}</h3>
            {incident?.category === "pump_failure" ? (
              <>
                <div className="response-cost">
                  <span>Estimated response cost</span>
                  <strong>{money(plan.cost)}</strong>
                </div>
                {plan.baseline_cost != null && (
                  <p className="saving">
                    {money(Math.max(0, plan.baseline_cost - plan.cost))} avoided
                    vs. no intervention
                  </p>
                )}
              </>
            ) : (
              <p className="fine-print">
                Inspection cost is not modeled by the backend.
              </p>
            )}
            {plan.actions.map((action, i) => (
              <p className="response-action" key={i}>
                {action.type === "dispatch_truck"
                  ? `${action.trucks} truck(s) × ${action.trips_per_truck} trip(s). First arrival: ${action.arrival_hours?.[0] != null ? "+" + formatValue(action.arrival_hours[0] * 60, 0) + " min" : "not provided"}.`
                  : action.type === "shut_in_wells"
                    ? `Shut in ${action.wells?.join(", ")} at +${formatValue(action.start_after_min, 0)} min.`
                    : `Inspect ${action.asset_id || "affected equipment"}.`}
              </p>
            ))}
            {plan.alternatives && (
              <details className="alternatives">
                <summary>
                  Calculated alternatives <ChevronRight size={13} />
                </summary>
                {plan.alternatives.map((p, i) => (
                  <div key={i}>
                    <span>
                      {p.label}
                      {p.tripped && <small>Includes automatic shut-in</small>}
                    </span>
                    <b>{money(p.cost)}</b>
                  </div>
                ))}
              </details>
            )}
            {plan.trace && (
              <details className="projection">
                <summary>
                  Projected tank response <ChevronRight size={13} />
                </summary>
                <SensorTrend
                  projected
                  points={plan.trace.map((p) => ({
                    ts: data.now + p.hour * 3600,
                    value: p.level_pct,
                  }))}
                  metric="level_pct"
                  unit="%"
                  thresholds={data.limits}
                />
                <p className="fine-print">
                  Backend simulation through repair. Not recorded telemetry.
                </p>
              </details>
            )}
            <details className="planning-limits">
              <summary>Verification & planning limits</summary>
              <p>{data.planning_scope}</p>
            </details>
            <p className="simulation-note">
              Recommendation only. No equipment commands or dispatches are sent.
            </p>
          </section>
        )}
        {facility && (
          <NemotronInvestigation
            dataset={dataset}
            facilityId={facility.id}
            at={data.now}
            disabled={disabled}
          />
        )}
        {asset.metrics.length > 0 && <details className="supporting-trend inspector-section"><summary>Sensor trend & technical details</summary>
            {metric && (
              <>
                <div className="chart-heading">
                  <span>{metricInfo[metric]?.label || metric}</span>
                  <code>{metric}</code>
                </div>
                {errors[metric] ? (
                  <p className="inline-error" role="alert">
                    {errors[metric]}
                  </p>
                ) : loading && !readings[metric] ? (
                  <p className="fine-print">Loading actual sensor readings…</p>
                ) : (
                  <SensorTrend
                    points={readings[metric] || []}
                    metric={metric}
                    unit={metricInfo[metric]?.unit || ""}
                    thresholds={
                      metric === "level_pct" ? data.limits : undefined
                    }
                  />
                )}
              </>
            )}
            <p className="fine-print">
              Sensor markers identify measured assets and metrics. Mounting
              positions are schematic.
            </p>        </details>}
      </div>
    </aside>
  );
}
