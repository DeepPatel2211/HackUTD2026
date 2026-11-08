"""Joint dispatch and well-shut-in timing, solved within the EOG plan model.

One facility chooses a no-action baseline or one simultaneous truck group with
equal trips per truck. Wells may shut independently at any time before repair.
The MILP retains every supplied truck/trip option and assigns actual reusable
vehicles; it does not use a cheapest-per-truck shortlist or an EDF schedule.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

# Millisecond-scale repair-boundary clearance and a small volume clearance keep
# numerical equality at a pickup from accidentally triggering automatic shut-in.
TIME_CLEARANCE = 1e-6


def solve(problems, option_lists, fleet):
    """Return (option, call hour, per-well shut hours, vehicle indices), or None.

    Solver success is required. Infeasibility is an expected result for an
    individual truck/trip option; limits/errors are never reported as optimal.
    Vehicle indices are internal scheduling resources, not fabricated truck IDs.
    """
    if not problems:
        return []
    if fleet < 0 or int(fleet) != fleet:
        raise ValueError('Fleet size must be a nonnegative integer')
    fleet = int(fleet)
    objective, upper, integer = [], [], []
    rows, lows, highs = [], [], []

    def variable(cost=0.0, hi=math.inf, binary=False):
        index = len(objective)
        objective.append(float(cost))
        upper.append(float(hi))
        integer.append(int(binary))
        return index

    def constraint(terms, lo=-math.inf, hi=math.inf):
        rows.append({key: value for key, value in terms.items() if value})
        lows.append(lo)
        highs.append(hi)

    def combine(*parts):
        result = {}
        for terms, scale in parts:
            for key, value in terms.items():
                result[key] = result.get(key, 0.0) + scale * value
        return result

    choices, starts, durations, demands = [], [], [], []
    largest_duration = 0.0
    for problem, options in zip(problems, option_lists):
        records, start, duration, demand = [], {}, {}, {}
        h = problem.horizon
        water = [max(0.0, value) / 24.0 for value in problem.water]
        margin = max(1e-6, problem.capacity * 1e-8)
        for option in options:
            trucks, trips = option['trucks'], option['trips']
            if trucks > fleet:
                continue
            if option.get('_baseline'):
                x = variable(option['_exact_cost'], 1, True)
                records.append((option, x, None, []))
                continue
            offsets = [problem.response_h + k * problem.cycle_h for k in range(trips)]
            latest = h - offsets[-1] - TIME_CLEARANCE if trucks else 0.0
            if latest < 0:
                continue
            busy = problem.busy_hours(trucks, trips)
            largest_duration = max(largest_duration, busy)
            x = variable(trucks * trips * problem.trip_cost + h * sum(problem.revenue), 1, True)
            d = variable(hi=max(0.0, latest))
            constraint({d: 1, x: -latest}, hi=0)
            shut = [variable(-revenue, h) for revenue in problem.revenue]
            for s in shut:
                constraint({s: 1, x: -h}, hi=0)
            # At repair, each well has produced only until its shut-in hour.
            end = {s: rate for s, rate in zip(shut, water)}
            end[x] = problem.initial - trucks * trips * problem.load - problem.limit + margin
            constraint(end, hi=0)
            for k, offset in enumerate(offsets):
                volume = {}
                for s, rate in zip(shut, water):
                    # u = min(call + trip offset, well shut-in), exactly.
                    u = variable(hi=h)
                    after_shut = variable(hi=1, binary=True)
                    constraint({after_shut: 1, x: -1}, hi=0)
                    constraint({u: 1, d: -1, x: -offset}, hi=0)
                    constraint({u: 1, s: -1}, hi=0)
                    constraint({d: 1, x: offset, u: -1, after_shut: -h}, hi=0)
                    constraint({s: 1, u: -1, x: -h, after_shut: h}, hi=0)
                    volume[u] = rate
                # Reach neither shutdown before pickup nor negative volume after it.
                quantity = trucks * problem.load
                before = dict(volume)
                before[x] = problem.initial - k * quantity - problem.limit + margin
                constraint(before, hi=0)
                after = dict(volume)
                after[x] = problem.initial - (k + 1) * quantity
                constraint(after, lo=0)
            records.append((option, x, d, shut))
            start[d] = 1.0
            duration[x] = busy
            demand[x] = trucks
        if not records:
            return None
        constraint({record[1]: 1 for record in records}, lo=1, hi=1)
        choices.append(records)
        starts.append(start)
        durations.append(duration)
        demands.append(demand)

    vehicles = [[variable(hi=1, binary=True) for _ in range(fleet)] for _ in problems]
    for assigned, demand in zip(vehicles, demands):
        constraint(combine(({v: 1 for v in assigned}, 1), (demand, -1)), lo=0, hi=0)
    # Identical vehicles can be renamed so the first facility uses a prefix.
    for left, right in zip(vehicles[0], vehicles[0][1:]):
        constraint({left: 1, right: -1}, lo=0)
    big = 2 * (max(p.horizon for p in problems) + largest_duration + 1)
    for i in range(len(problems)):
        for j in range(i + 1, len(problems)):
            for vehicle in range(fleet):
                order = variable(hi=1, binary=True)
                yi, yj = vehicles[i][vehicle], vehicles[j][vehicle]
                constraint(combine((starts[i], 1), (durations[i], 1), (starts[j], -1),
                                   ({yi: big, yj: big, order: big}, 1)), hi=3 * big)
                constraint(combine((starts[j], 1), (durations[j], 1), (starts[i], -1),
                                   ({yi: big, yj: big, order: -big}, 1)), hi=2 * big)

    rr, cc, vv = [], [], []
    for index, terms in enumerate(rows):
        for key, value in terms.items():
            rr.append(index)
            cc.append(key)
            vv.append(value)
    matrix = coo_matrix((vv, (rr, cc)), shape=(len(rows), len(objective))).tocsc()
    result = milp(np.asarray(objective), integrality=np.asarray(integer),
                  bounds=Bounds(np.zeros(len(objective)), upper),
                  constraints=LinearConstraint(matrix, lows, highs),
                  options={'mip_rel_gap': 0.0, 'presolve': True})
    if result.status == 2:
        return None
    if not result.success or result.status != 0:
        raise RuntimeError(f'Fleet optimization did not complete: {result.message}')
    answer = []
    for i, records in enumerate(choices):
        option, _, d, shut = next(record for record in records if result.x[record[1]] > 0.5)
        answer.append((option, max(0.0, float(result.x[d])) if d is not None else 0.0,
                       [min(problems[i].horizon, max(0.0, float(result.x[s]))) for s in shut],
                       [index for index, v in enumerate(vehicles[i]) if result.x[v] > 0.5]))
    return answer
