import { useState } from 'react';
import { ChevronDown, ChevronRight, Network } from 'lucide-react';
import type { Dashboard, Incident, Navigation } from '../../lib/types';

export default function NetworkContext({ data, navigation, onNavigate, onIncident }: {
  data: Dashboard; navigation: Navigation; onNavigate: (nav: Navigation) => void; onIncident: (incident: Incident) => void;
}) {
  const [collapsed, setCollapsed] = useState(true);
  const system = data.systems.find(s => s.id === navigation.systemId);
  if (!system) return null;
  const facilities = data.facilities.filter(f => f.system_id === system.id);
  const incidents = data.alerts.filter(a => a.system_id === system.id);
  return <aside className={`network-context glass ${collapsed ? 'collapsed' : ''}`} aria-label="Selected system summary">
    <button className="context-toggle" onClick={() => setCollapsed(value => !value)} aria-expanded={!collapsed}>
      <Network size={17}/><span>System {system.id}<small>{facilities.length} facilities · {incidents.length} incidents</small></span><ChevronDown size={15}/>
    </button>
    {!collapsed && <div className="context-content">
      <p>Disposal site <strong>{system.disposal_site.id}</strong></p>
      <h3>Facilities</h3>{facilities.map(f => <button key={f.id} onClick={() => onNavigate({ systemId: system.id, facilityId: f.id })}><span>{f.id.replace(/^.*_FACILITY_/, 'Facility ')}</span><ChevronRight size={14}/></button>)}
      {incidents.length > 0 && <><h3>Investigate</h3>{incidents.map(a => <button key={`${a.facility_id}:${a.category}`} onClick={() => onIncident(a)}><span>{a.facility_id.replace(/^.*_FACILITY_/, 'Facility ')} · {a.category.replaceAll('_',' ')}</span><ChevronRight size={14}/></button>)}</>}
    </div>}
  </aside>;
}
