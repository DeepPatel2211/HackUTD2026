import { Activity, Building2, CheckCircle2, Layers3, OctagonAlert, TriangleAlert } from 'lucide-react';
import type { Dashboard } from '../../lib/types';

export default function StatusStrip({ data }: { data: Dashboard }) {
  const metrics = [
    { label: 'Systems', value: data.systems.length, icon: Layers3, tone: 'cyan' },
    { label: 'Facilities', value: data.facilities.length, icon: Building2, tone: 'cyan' },
    { label: 'Active incidents', value: data.alerts.length, icon: Activity, tone: 'red' },
    { label: 'Pump failures', value: data.alerts.filter(a => a.category === 'pump_failure').length, icon: OctagonAlert, tone: 'amber' },
    { label: 'Degradation', value: data.alerts.filter(a => a.category === 'pump_degradation').length, icon: TriangleAlert, tone: 'amber' },
    { label: 'Clear systems', value: data.systems.filter(s => !data.alerts.some(a => a.system_id === s.id)).length, icon: CheckCircle2, tone: 'green' },
  ];
  return <section className="status-strip" aria-label="Recorded network summary">{metrics.map(({ label, value, icon: Icon, tone }) => <div className={`status-metric tone-${tone}`} key={label}><Icon size={25} strokeWidth={1.5}/><span><strong>{value}</strong><small>{label}</small></span></div>)}</section>;
}
