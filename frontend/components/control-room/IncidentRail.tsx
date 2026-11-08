import { AlertTriangle, ChevronDown, ChevronUp, ShieldCheck, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import type { Incident } from '../../lib/types';
import { humanize } from '../../lib/operational-status';

export default function IncidentRail({ incidents, open, onToggle, onSelect, selectedFacility, disabled, systemId }: {
  incidents: Incident[]; open: boolean; onToggle: () => void;
  onSelect: (incident: Incident) => void; selectedFacility?: string; disabled: boolean; systemId?: string;
}) {
  const [filter, setFilter] = useState<string | null>(null);
  const groups = [...new Set(incidents.map(a => a.system_id))];
  const requested = filter ?? systemId ?? 'all';
  const active = groups.includes(requested) ? requested : 'all';
  const visible = active === 'all' ? incidents : incidents.filter(a => a.system_id === active);
  return <aside className={`incident-rail ${open ? 'expanded' : 'collapsed'} ${!incidents.length ? 'no-alerts' : ''}`} aria-label="Active incidents">
    <button className="rail-heading" aria-expanded={open} onClick={onToggle}>
      {incidents.length ? <AlertTriangle size={22}/> : <ShieldCheck size={22}/>}<span><b>Incidents <em>{incidents.length}</em></b></span>
      {open ? <ChevronUp size={15}/> : <ChevronDown size={15}/>}
    </button>
    {open && <>
      <label className="incident-scope">
        <span>Alert scope</span>
        <select aria-label="Filter incidents by system" value={active} onChange={event => setFilter(event.target.value)}>
          <option value="all">All field ({incidents.length})</option>
          {groups.map(id => <option key={id} value={id}>{id} ({incidents.filter(a => a.system_id === id).length})</option>)}
        </select>
      </label>
      <div className="incident-scroll">
        {!visible.length && <div className="no-incidents"><ShieldCheck size={24}/><strong>No active incidents</strong><span>at this recorded moment.</span></div>}
        {visible.map(incident => <button key={`${incident.facility_id}:${incident.category}`}
          className={`incident-row ${incident.category === 'pump_degradation' ? 'severity-warning' : 'severity-critical'} ${selectedFacility === incident.facility_id ? 'selected' : ''}`}
          title={`${incident.facility_id} - ${humanize(incident.category)}`} aria-current={selectedFacility === incident.facility_id ? 'true' : undefined}
          disabled={disabled} onClick={() => onSelect(incident)}>
          <AlertTriangle className="incident-symbol" size={21}/>
          <span className="incident-copy"><strong>{incident.facility_id.replace(/^.*_FACILITY_/, 'Facility ')}</strong><span>{incident.system_id}{' \u00b7 '}{humanize(incident.category).toLowerCase()}</span></span>
          <span className="incident-urgency">{incident.category === 'pump_failure' && incident.hours_to_limit != null ? <><strong>{incident.hours_to_limit.toFixed(1)}<small>h</small></strong><span>to shutdown</span></> : <span className="inspection-note">Inspection</span>}</span>
          <ChevronRight className="incident-chevron" size={14}/>
        </button>)}
      </div>
    </>}
  </aside>;
}
