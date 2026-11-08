"""Deciding what to do about a pump failure, and what it costs.

A failed pump means the tank has no outlet. Well water keeps arriving, the level
climbs, and when it reaches the shutdown limit the facility's wells trip off and
earn nothing until the repair finishes. The operator has three levers:

  * send trucks        -- flat price per trip, fixed barrels per trip, and the
                          truck is unavailable until it has driven back
  * shut in wells early-- the tank fills slower, but a shut well earns nothing
  * do nothing         -- accept the automatic trip and lose every well

Everything here is a deterministic simulation of the tank, so a plan is never
"recommended" on a rule of thumb: it is recommended because we replayed it and
checked its final scheduled actions. Optimality is limited to the explicit
truck-group/constant-inflow model, not unrestricted field operations.

The subtle part is that a system's trucks are shared. When two or three pumps in
one system fail within a few hours, a truck sent to one tank cannot help another,
so the plans have to be chosen together rather than one facility at a time.
"""
from __future__ import annotations

import math
from statistics import mean as _mean, pstdev

from .scheduling import solve

# Standard normal deviate for a 10%/90% interval, used for the countdown range.
Z80 = 1.2816


# --------------------------------------------------------------------------
# The tank simulator
# --------------------------------------------------------------------------

def simulate(capacity, limit, initial, horizon, water, revenue,
             shut, shut_at, arrivals, load, trip_cost, already_tripped=False):
    """Replay one plan against the tank and return its cost, or None if illegal.

    Arguments are in plain units so the maths stays inspectable:
      capacity  tank size in bbl              limit     shutdown level in bbl
      initial   current volume in bbl         horizon   hours until the repair ends
      water     each well's water rate, bpd   revenue   each well's lost $/hour
      shut      indices of wells to shut in   shut_at   hour, or {well index: hour}
      arrivals  hours at which truck trips land (repeated once per truck)
      load      bbl removed per trip          trip_cost $ per trip

    This integrates exactly rather than stepping a clock: the tank's level is
    piecewise linear, so we only need to evaluate it where something changes --
    a truck landing, the shut-in starting, the repair ending. Between those the
    level moves at a constant rate, so the crossing of the shutdown limit can be
    solved for directly instead of searched for.

    Returns None when the plan is physically impossible, which is how the search
    discards trips that would draw more water than the tank is holding.
    """
    if any(not math.isfinite(t) or t < 0 or t >= horizon - 1e-9 for t in arrivals):
        return None
    starts = {i: (shut_at[i] if isinstance(shut_at, dict) else shut_at) for i in shut}
    if any(not math.isfinite(t) or t < 0 or t > horizon for t in starts.values()):
        return None
    volume = initial
    cost = len(arrivals) * trip_cost
    tripped = already_tripped or initial >= limit - 1e-7
    trace = [{'hour': 0.0, 'level_pct': 100 * volume / capacity}]
    previous = 0.0

    # Every moment the picture changes, in order. Anything outside the repair
    # window is irrelevant: the pump is back before it and the tank is safe after.
    moments = sorted({0.0, horizon} | set(starts.values()) | set(arrivals))

    for moment in moments:
        if moment < 0 or moment > horizon:
            continue
        # Wells still producing over the segment that just ended.
        stopped = {i for i, start in starts.items() if previous >= start}
        producing = [i for i in range(len(water)) if i not in stopped]
        inflow = 0.0 if tripped else sum(water[i] for i in producing) / 24.0  # bbl/hour
        span = moment - previous

        if tripped:
            # Automatic shut-in: every well in the facility is earning nothing.
            cost += sum(revenue) * span
        else:
            cost += sum(revenue[i] for i in stopped) * span
            # How long until this segment's inflow would reach the limit?
            to_limit = (limit - volume) / inflow if inflow > 0 else math.inf
            if to_limit < span - 1e-8 or (to_limit <= span + 1e-9 and moment < horizon - 1e-8):
                # The tank trips partway through this segment.
                cost += sum(revenue[i] for i in producing) * max(0.0, span - to_limit)
                trace.append({'hour': round(previous + max(0.0, to_limit), 9),
                              'level_pct': 100 * limit / capacity})
                volume, tripped = limit, True
            else:
                volume += inflow * span

        trace.append({'hour': round(moment, 9), 'level_pct': 100 * volume / capacity})

        if moment in arrivals:
            # Trucks landing at this instant each take a full load.
            removed = arrivals.count(moment) * load
            if removed > volume + 1e-6:
                return None  # cannot haul water that is not in the tank
            volume -= removed
            trace.append({'hour': round(moment, 9), 'level_pct': 100 * volume / capacity})

        previous = moment

    return {'cost': round(cost, 2), '_exact_cost': cost, 'tripped': tripped, 'trace': trace, 'verified': True}


# --------------------------------------------------------------------------
# Countdown
# --------------------------------------------------------------------------

def hours_to_limit(level_pct, capacity, limit_pct, inflow_samples):
    """How long until this tank trips, with an honest uncertainty band.

    The headroom is exact -- it is just tank geometry. The fill rate is not: it is
    a noisy sensor sum that also moves as wells breathe. So we take the spread of
    the recent inflow readings, turn it into a standard error of the mean, and
    report the countdown as a range. A faster-than-expected inflow gives the
    shorter time, which is why p10 uses the high end of the inflow band.

    Returns a dict of p50/p10/p90 hours, or zeroes if the tank is already at limit.
    """
    headroom = max(0.0, (limit_pct - level_pct) / 100.0 * capacity)  # bbl
    rates = [v for v in inflow_samples if v > 0]
    if not rates or headroom <= 0:
        return {'p50': 0.0, 'p10': 0.0, 'p90': 0.0, 'inflow_bpd': rates[-1] if rates else 0.0}

    centre = _mean(rates)
    # Standard error of the mean inflow; with one sample we fall back to no spread.
    spread = (pstdev(rates) / math.sqrt(len(rates))) if len(rates) > 1 else 0.0
    fast = max(centre + Z80 * spread, 1e-6)   # fills quickest -> least time
    slow = max(centre - Z80 * spread, 1e-6)   # fills slowest  -> most time
    return {
        'p50': headroom / (centre / 24.0),
        'p10': headroom / (fast / 24.0),
        'p90': headroom / (slow / 24.0),
        'inflow_bpd': centre,
    }


# --------------------------------------------------------------------------
# Candidate plans for one failed pump
# --------------------------------------------------------------------------

class FacilityProblem:
    """Everything the planner needs about one tank that is filling up."""

    def __init__(self, data, facility, level_pct, horizon_h, water, revenue, now=None):
        system = data.system_of[facility['id']]
        travel = data.ops['systems'][system['id']]['facilities'][facility['id']]
        trucking = data.ops['emergency_trucking']

        self.facility = facility
        self.facility_id = facility['id']
        self.system_id = system['id']
        self.capacity = facility['tank']['capacity_bbl']
        self.limit = self.capacity * data.limits['shutdown'] / 100.0   # bbl
        self.initial = self.capacity * level_pct / 100.0               # bbl
        self.horizon = max(0.0, horizon_h)
        self.water = water          # bbl/day per well, as measured right now
        self.revenue = revenue      # $/hour per well
        self.response_h = travel['response_min'] / 60.0
        self.cycle_h = travel['cycle_min'] / 60.0
        self.load = trucking['truck_capacity_bbl']
        self.trip_cost = trucking['cost_per_trip']
        self.fleet = data.ops['systems'][system['id']]['emergency_fleet_size']
        self.already_tripped = self.initial >= self.limit - 1e-7 or bool(
            now is not None and facility['wells'] and
            all(data.value(w['id'], 'status', now, 1) == 0 for w in facility['wells']))
        if self.capacity <= 0 or self.response_h < 0 or self.cycle_h <= 0:
            raise ValueError('Invalid tank capacity or truck travel times')


    def run(self, shut, shut_at, arrivals):
        """Replay one specific plan on this tank."""
        return simulate(self.capacity, self.limit, self.initial, self.horizon,
                        self.water, self.revenue, shut, shut_at, arrivals,
                        self.load, self.trip_cost, already_tripped=self.already_tripped)

    def arrivals(self, trucks, trips, delay=0.0):
        """When each truck trip lands, given the dispatch is called at `delay` hours.

        Per the rules every truck in a plan is called together and arrives
        `response_min` later; a truck that goes back for more returns every
        `cycle_min`. A trip that would land after the repair is finished is not a
        trip at all, so it is dropped rather than charged for.
        """
        times = []
        for trip in range(trips):
            when = delay + self.response_h + trip * self.cycle_h
            if when >= self.horizon - 1e-9:
                break
            times.extend([when] * trucks)
        return times

    def busy_hours(self, trucks, trips):
        """How long each dispatched truck is tied up: out, back, and ready again."""
        if not trucks or not trips:
            return 0.0
        return self.response_h + (trips - 1) * self.cycle_h + self.cycle_h

    def max_trips(self, delay=0.0):
        """Most trips one truck can land inside the remaining repair window."""
        usable = self.horizon - delay - self.response_h
        return 0 if usable <= 1e-9 else math.ceil((usable - 1e-9) / self.cycle_h)


def _baseline(problem):
    result = problem.run([], problem.horizon, [])
    return {**result,
            'label': 'Accept the automatic shut-in' if result['tripped'] else 'No action needed',
            'trucks': 0, 'trips': 0, 'delay_h': 0.0, 'latest_delay_h': 0.0,
            'busy_h': 0.0, 'shut_wells': [], 'shut_at_h': None,
            'actions': [{'type': 'none'}], 'baseline_cost': result['cost'], '_baseline': True}


def _materialize(problem, option, delay, shut_times):
    """Serialize final times FIRST, then simulate exactly those public actions."""
    if option.get('_baseline'):
        return _baseline(problem)
    trucks, trips = option['trucks'], option['trips']
    delay = round(max(0.0, delay) * 60, 9) / 60
    arrivals = problem.arrivals(trucks, trips, delay)
    if len(arrivals) != trucks * trips:
        raise RuntimeError('Scheduled trips do not all arrive before repair')
    times = sorted({round(t, 9) for t in arrivals})
    starts = {i: round(start * 60, 9) / 60 for i, start in enumerate(shut_times)
              if start < problem.horizon - 1e-9}
    actions = []
    busy_until = round(delay + problem.busy_hours(trucks, trips), 9)
    if trucks:
        actions.append({'type': 'dispatch_truck', 'facility_id': problem.facility_id,
                        'trucks': trucks, 'trips_per_truck': trips,
                        'arrival_hours': times, 'busy_until_hour': busy_until})
    grouped = {}
    for index, start in starts.items():
        grouped.setdefault(start, []).append(problem.facility['wells'][index]['id'])
    for start, wells in sorted(grouped.items()):
        actions.append({'type': 'shut_in_wells', 'wells': wells,
                        'start_after_min': round(start * 60, 9)})
    actual_arrivals = [t for t in times for _ in range(trucks)]
    result = problem.run(list(starts), starts, actual_arrivals)
    if result is None or result['tripped']:
        raise RuntimeError('Final scheduled actions failed tank verification')
    base = _baseline(problem)
    parts = [f'{trucks} truck{"s" if trucks != 1 else ""}, {trips} trip{"s" if trips != 1 else ""} each'] if trucks else []
    for start, wells in sorted(grouped.items()):
        when = 'now' if start < 1e-6 else f'in {start * 60:.1f} min'
        parts.append(f'shut in {", ".join(wells)} {when}')
    return {**result, 'label': ' + '.join(parts) or 'No action needed',
            'trucks': trucks, 'trips': trips, 'delay_h': delay,
            'latest_delay_h': delay, 'busy_h': problem.busy_hours(trucks, trips),
            'shut_wells': [problem.facility['wells'][i]['id'] for i in starts],
            'shut_at_h': min(starts.values()) if starts else None,
            'actions': actions or [{'type': 'none'}], 'baseline_cost': base['cost'],
            '_baseline': False}


def candidates(problem):
    """Keep ALL feasible truck/trip options; independent well times are optimized.

    The individual result is a lower-cost bound/preview, not a frozen schedule:
    allocate() jointly re-solves the dispatch and every well's shut-in time.
    """
    baseline = _baseline(problem)
    if baseline['cost'] == 0 or problem.already_tripped or problem.horizon <= 0:
        return [baseline]
    plans = [baseline]
    for trucks in range(problem.fleet + 1):
        trip_counts = range(1, problem.max_trips() + 1) if trucks else [0]
        for trips in trip_counts:
            option = {'trucks': trucks, 'trips': trips, '_baseline': False}
            result = solve([problem], [[option]], problem.fleet)
            if result is not None:
                _, delay, starts, _ = result[0]
                plans.append(_materialize(problem, option, delay, starts))
    plans.sort(key=lambda plan: (plan['cost'], plan['trucks'], plan['trips']))
    return plans


def _schedulable(jobs, fleet):
    """Exact order search for fixed-duration jobs with latest-start deadlines.

    Retained for callers checking fixed plans. EDF by latest start is NOT exact,
    even for one truck. Joint cost/timing optimization below uses the MILP.
    """
    failed = set()

    def visit(remaining, free, calls):
        if not remaining:
            return calls
        state = (remaining, tuple(sorted(free)))
        if state in failed:
            return None
        for index in remaining:
            key, trucks, duration, latest = jobs[index]
            if not 0 < trucks <= fleet:
                continue
            order = sorted(range(fleet), key=lambda i: free[i])[:trucks]
            start = max(free[i] for i in order)
            if start > latest + 1e-9:
                continue
            after = list(free)
            for truck in order:
                after[truck] = start + duration
            answer = visit(tuple(i for i in remaining if i != index), after, {**calls, key: start})
            if answer is not None:
                return answer
        failed.add(state)
        return None

    return visit(tuple(range(len(jobs))), [0.0] * fleet, {})


def allocate(problems, plan_options, fleet, keep=None):
    """Jointly optimize every retained option, dispatch and independent well time.

    `keep` is accepted for compatibility but never truncates candidates. The
    returned trace/cost/actions are rebuilt from the FINAL shared-fleet schedule.
    """
    options = [plan_options[p.facility_id] for p in problems]
    result = solve(problems, options, fleet)
    if result is None:
        raise RuntimeError('No legal shared-fleet allocation, including no-action baselines')
    plans, intervals = [], []
    for problem, (option, delay, starts, vehicles) in zip(problems, result):
        plan = _materialize(problem, option, delay, starts)
        for truck in vehicles:
            intervals.append((truck, plan['delay_h'], plan['delay_h'] + plan['busy_h']))
        plans.append(plan)
    for truck in range(fleet):
        assigned = sorted((start, end) for vehicle, start, end in intervals if vehicle == truck)
        if any(end > following + 1e-7 for (_, end), (following, _) in zip(assigned, assigned[1:])):
            raise RuntimeError('Final schedule double-books a truck')
    return plans


def reuse_possible(data) -> bool:
    """Check real ordered facility pairs, using the FIRST facility's cycle."""
    horizon = data.ops['expected_repair_hours']['pump_failure']
    return any((a['response_min'] + a['cycle_min'] + b['response_min']) / 60 < horizon
               for system in data.ops['systems'].values()
               for aid, a in system['facilities'].items()
               for bid, b in system['facilities'].items() if aid != bid)
