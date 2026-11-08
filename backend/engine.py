"""Telemetry-only detection and deterministic, event-based planning."""
import csv
import json
import itertools
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'eog'


class Dataset:
    def __init__(self, name):
        folder = (ROOT / name).resolve()
        if not folder.is_relative_to(ROOT.resolve()):
            raise ValueError('Dataset must be inside data/eog')
        self.network = json.loads((folder / 'network.json').read_text())
        self.ops = json.loads((folder / 'ops.json').read_text())
        self.series = {}
        with (folder / 'telemetry.csv').open(newline='') as file:
            for r in csv.DictReader(file):
                self.series.setdefault((r['asset_id'], r['metric']), []).append((int(r['ts_unix']), float(r['value'])))
        if not self.series:
            raise ValueError('Empty telemetry')
        for series in self.series.values():
            series.sort()
        self.start = min(v[0][0] for v in self.series.values())
        self.end = max(v[-1][0] for v in self.series.values())

    def values(self, asset, metric, now):
        import bisect
        series = self.series.get((asset, metric), [])
        return series[:bisect.bisect_right(series, (now, float('inf')))]

    def value(self, asset, metric, now, default=0):
        values = self.values(asset, metric, now)
        return values[-1][1] if values else default

    def analyze(self, now=None):
        now = self.end if now is None else max(self.start, min(now, self.end))
        facilities, alerts = [], []
        for system in self.network['systems']:
            for f in system['facilities']:
                pid, lid = f['pump']['id'], f['pipeline']['id']
                level = self.value(f['tank']['id'], 'level_pct', now)
                flow = self.value(pid, 'flow_bpd', now)
                received = self.value(lid, 'receive_flow_bpd', now)
                status = self.value(pid, 'status', now)
                category, evidence, onset = None, [], now
                if status == 2:
                    category = 'pump_failure'
                    for ts, val in reversed(self.values(pid, 'status', now)):
                        if val != 2:
                            break
                        onset = ts
                    evidence = ['Pump reports fault status 2.', f'Pump discharge flow is {flow:.0f} bbl/day.']
                else:
                    recent = self.values(pid, 'flow_bpd', now)[-288:]
                    running = [(ts, v) for ts, v in recent if self.value(pid, 'status', ts) == 1 and v > 0][-12:]
                    # Retain evidence across normal pump-off cycles; use medians to suppress sensor noise.
                    if len(running) >= 8:
                        receipt_ratio = median(self.value(lid, 'receive_flow_bpd', ts)/v for ts,v in running)
                        rated_ratio = median(v/f['pump']['max_flow_bpd'] for _,v in running)
                        if receipt_ratio < .98:
                            category, onset = 'pipeline_leak', running[0][0]
                            evidence = [f'Median pipeline receipt is {receipt_ratio*100:.1f}% of pump flow across {len(running)} running samples.', 'Evidence retained through normal pump-off cycles.']
                        elif rated_ratio < .985:
                            category, onset = 'pump_degradation', running[0][0]
                            evidence = [f'Median running flow is {rated_ratio*100:.1f}% of rated capacity across {len(running)} samples.', 'Evidence retained through normal pump-off cycles.']
                item = dict(f, system_id=system['id'], level_pct=level, pump_status=status, flow_bpd=flow, category=category)
                facilities.append(item)
                if category:
                    water = [max(0, self.value(w['id'], 'water_bpd', now)) for w in f['wells']]
                    rates = [(w['oil_bpd'] * self.ops['prices']['oil_per_bbl'] + w['gas_mcfd'] * self.ops['prices']['gas_per_mcf']) / 24 for w in f['wells']]
                    limit = self.network['defaults']['tank_limits_pct']['shutdown']
                    hours = max(0, (limit-level)/100*f['tank']['capacity_bbl']/(sum(water)/24)) if sum(water) else 0
                    alert = dict(facility_id=f['id'], system_id=system['id'], category=category, onset_unix=onset, evidence=evidence, confidence=.99 if category == 'pump_failure' else .85, hours_to_limit=hours if category == 'pump_failure' else None, revenue_per_hour=sum(rates))
                    if category == 'pump_failure':
                        horizon = max(0, self.ops['expected_repair_hours']['pump_failure']-(now-onset)/3600)
                        alert['candidates'] = candidates(f, self.ops, system['id'], level, limit, horizon, water, rates)
                    else:
                        alert['recommendation'] = {'label': 'Urgent field inspection' if category == 'pipeline_leak' else 'Request pump inspection', 'cost': 0, 'actions': [{'type':'field_inspection', 'asset_id':lid if category == 'pipeline_leak' else pid}]}
                    alerts.append(alert)
        for sid, group in itertools.groupby(sorted([a for a in alerts if a['category']=='pump_failure'], key=lambda a:a['system_id']), key=lambda a:a['system_id']):
            group = list(group)
            # Reserve each truck for its entire job; overlapping jobs cannot double-book it.
            # Conservative: trucks are not reassigned to another facility within this horizon.
            fleet = self.ops['systems'][sid]['emergency_fleet_size']
            states = {0: (0, [])}
            for a in group:
                next_states = {}
                for used, (cost, plans) in states.items():
                    for plan in a['candidates']:
                        n = used + plan['trucks']
                        if n <= fleet and (n not in next_states or cost+plan['cost'] < next_states[n][0]):
                            next_states[n] = (cost+plan['cost'], plans+[plan])
                states = next_states
            selected = min(states.values(), key=lambda v:v[0])[1]
            for a, plan in zip(group, selected):
                a['recommendation'] = plan
        alerts.sort(key=lambda a:(a['category']!='pump_failure', a['hours_to_limit'] if a['hours_to_limit'] is not None else 1e9, -a['revenue_per_hour']))
        return dict(now=now, start=self.start, end=self.end, systems=self.network['systems'], facilities=facilities, alerts=alerts, limits=self.network['defaults']['tank_limits_pct'], planning_scope='Best verified candidate; simultaneous truck jobs, common timed well shut-in. Cross-facility truck reuse and independently timed well shut-ins are not searched.')


def simulate(capacity, limit, initial, horizon, water, revenue, shut, shut_at, arrivals, load, trip_cost):
    """Integrate exactly between arrivals, shut-in, repair and safety trip."""
    volume, cost, tripped = initial, len(arrivals)*trip_cost, initial >= limit-1e-7
    trace = [{'hour':0, 'level_pct':100*volume/capacity}]
    previous = 0
    for t in sorted(set([0, horizon, shut_at] + arrivals)):
        if t < 0 or t > horizon:
            continue
        active = [i for i in range(len(water)) if not (i in shut and previous >= shut_at)]
        inflow = sum(water[i] for i in active)/24 if not tripped else 0
        dt = t-previous
        if tripped:
            cost += sum(revenue)*dt
        else:
            cost += sum(revenue[i] for i in shut)*dt if previous >= shut_at else 0
            until = (limit-volume)/inflow if inflow else float('inf')
            if until < dt-1e-8 or (until <= dt+1e-9 and t < horizon-1e-8):
                cost += sum(revenue[i] for i in active)*max(0,dt-until)
                volume, tripped = limit, True
            else:
                volume += inflow*dt
        trace.append({'hour':round(t,6), 'level_pct':100*volume/capacity})
        if t in arrivals:
            amount = arrivals.count(t)*load
            if amount > volume+1e-6:
                return None
            volume -= amount
            trace.append({'hour':round(t,6), 'level_pct':100*volume/capacity})
        previous = t
    return dict(cost=round(cost,2), tripped=tripped, trace=trace, verified=True)


def candidates(f, ops, sid, level, limit_pct, horizon, water, revenue):
    cap = f['tank']['capacity_bbl']; initial = cap*level/100; limit = cap*limit_pct/100
    travel = ops['systems'][sid]['facilities'][f['id']]
    fleet = ops['systems'][sid]['emergency_fleet_size']
    load = ops['emergency_trucking']['truck_capacity_bbl']; price = ops['emergency_trucking']['cost_per_trip']
    def run(shut, at, arrivals):
        return simulate(cap, limit, initial, horizon, water, revenue, shut, at, arrivals, load, price)
    base = run([], horizon, [])
    plans = [dict(base, label='Accept automatic shutdown' if base['tripped'] else 'Monitor until repair', trucks=0, actions=[], baseline_cost=base['cost'])]
    if initial >= limit-1e-7 or horizon <= 0:
        return plans
    for trucks in range(fleet+1):
        max_trips = max(0, int((horizon*60-travel['response_min']-1e-6)//travel['cycle_min'])+1) if trucks else 0
        for trips in range(1 if trucks else 0, max_trips+1):
            arrivals = [(travel['response_min']+j*travel['cycle_min'])/60 for j in range(trips) for _ in range(trucks)]
            for mask in range(1 << len(water)):
                shut = [i for i in range(len(water)) if mask & (1 << i)]
                at = horizon
                result = run(shut, at, arrivals)
                if result is None or result['tripped']:
                    if not shut:
                        continue
                    result = run(shut, 0, arrivals)
                    if result is None or result['tripped']:
                        continue
                    lo, hi = 0, horizon
                    for _ in range(32):
                        mid = (lo+hi)/2
                        trial = run(shut, mid, arrivals)
                        if trial is not None and not trial['tripped']:
                            lo = mid
                        else:
                            hi = mid
                    at = max(0, lo-1e-6)
                    result = run(shut, at, arrivals)
                actions = []
                if trucks:
                    actions.append(dict(type='dispatch_truck', facility_id=f['id'], trucks=trucks, trips_per_truck=trips, arrival_hours=sorted(set(arrivals)), busy_until_hour=arrivals[-1]+travel['cycle_min']/60))
                if shut and at < horizon-1e-5:
                    actions.append(dict(type='shut_in_wells', wells=[f['wells'][i]['id'] for i in shut], start_after_min=round(at*60,2)))
                label = ' + '.join(([f'{trucks} truck(s), {trips} trip(s) each'] if trucks else []) + ([f'Shut {len(shut)} well(s) at +{at*60:.0f} min'] if shut and at < horizon-1e-5 else [])) or 'Monitor until repair'
                plans.append(dict(result, label=label, trucks=trucks, actions=actions, baseline_cost=base['cost']))
    # One cheapest candidate for each fleet allocation is sufficient for joint selection.
    best = {}
    for p in plans:
        if p['trucks'] not in best or p['cost'] < best[p['trucks']]['cost']:
            best[p['trucks']] = p
    alternatives = sorted(plans, key=lambda p:p['cost'])
    for p in best.values():
        p['alternatives'] = [dict(label=x['label'], cost=x['cost'], tripped=x['tripped']) for x in [plans[0]]+alternatives[:5]]
    return list(best.values())
