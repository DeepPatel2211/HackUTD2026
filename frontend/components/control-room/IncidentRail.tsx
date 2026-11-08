import { Activity, ChevronDown, ChevronUp, CircleAlert, Clock3, ShieldCheck } from 'lucide-react';
import type { Incident } from '../../lib/types';
import { humanize } from '../../lib/operational-status';

export default function IncidentRail({ incidents, open, onToggle, onSelect, selectedFacility, disabled }: {
  incidents: Incident[]; open: boolean; onToggle: () => void;
  onSelect: (incident: Incident) => void; selectedFacility?: string; disabled: boolean;
}) {
  return <aside className={`incident-rail glass ${open ? 'expanded' : 'collapsed'}`} aria-label="Active incidents">
    <button className="rail-heading" aria-expanded={open} onClick={onToggle}>
      <Activity size={18}/><b>Active incidents</b><span className="incident-count">{incidents.length}</span>
      {open ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
    </button>
    {open && <div className="incident-scroll">
      <p className="rail-context">Recorded events · priority order</p>
      {!incidents.length && <div className="no-incidents"><ShieldCheck size={24}/><strong>No active incidents</strong><span>at this recorded moment.</span></div>}
      {incidents.map(incident => <button key={`${incident.facility_id}:${incident.category}`}
        className={`incident-row ${incident.category === 'pump_degradation' ? 'severity-warning' : 'severity-critical'} ${selectedFacility === incident.facility_id ? 'selected' : ''}`}
        title={`${incident.facility_id} · ${humanize(incident.category)}`} aria-current={selectedFacility === incident.facility_id ? 'true' : undefined}
        disabled={disabled} onClick={() => onSelect(incident)}>
        <CircleAlert className="incident-symbol" size={16}/>
        <span className="incident-copy"><strong>{incident.facility_id.replace(/^.*_FACILITY_/, 'Facility ')}</strong><span>{humanize(incident.category)}</span><small>System {incident.system_id}</small></span>
        <span className="incident-urgency">{incident.category === 'pump_failure' && incident.hours_to_limit != null ? <><strong>{incident.hours_to_limit.toFixed(1)}<small> h</small></strong><span><Clock3 size={11}/>to shutdown</span></> : <span>Inspection<br/>required</span>}</span>
      </button>)}
    </div>}
  </aside>;
}
