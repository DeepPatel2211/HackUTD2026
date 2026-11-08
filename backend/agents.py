"""Three-tier Nemotron agent layer over the deterministic engine.

    System agent     one per system   owns the shared trucks and the disposal site
    Facility agent   one per facility reconciles its components, weighs the plan
    Component agent  one per asset    reports only what its own sensors recorded

The split is deliberate. Every number in this file is computed in Python before
any model is called: costs, countdowns, plan selection and truck scheduling stay
in engine.py and planner.py, where the MILP can prove them. The agents receive
those numbers as a payload and are asked only to explain them. They never
calculate, and `unsupported_numbers` rejects any figure they produce that is not
in the payload they were handed, so "no invented data" is enforced rather than
requested.

Agents are therefore an explanation tier, not a decision tier. An agent may say
it disagrees with the plan -- that becomes visible text -- but it cannot change
what the operator is told to do.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from . import config

# Component agents are small and numerous; the reasoning tiers are few and slow.
# Eight in flight keeps a facility's components effectively simultaneous without
# opening enough sockets to trip a rate limit.
MAX_CONCURRENT = 8
REQUEST_TIMEOUT = 120.0

# A retry costs a second and buys a much better chance of a clean answer, but a
# second failure means the model is not going to comply and we render the
# payload ourselves instead.
MAX_ATTEMPTS = 2

_NUMBER = re.compile(r'-?\d[\d,]*\.?\d*')

# Counts and ordinals a model will legitimately write while describing a payload
# ("two of three wells", "the first trip"). Rejecting these produces nothing but
# false alarms, so small integers are allowed through the validator.
_FREE_INTEGERS = set(range(0, 13))


# --------------------------------------------------------------------------
# Guarding against invented numbers
# --------------------------------------------------------------------------

def _payload_numbers(value, into: set[float]) -> None:
    """Collect every number reachable in a payload, at any nesting depth."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        into.add(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            _payload_numbers(item, into)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _payload_numbers(item, into)
    elif isinstance(value, str):
        for match in _NUMBER.finditer(value):
            try:
                into.add(float(match.group().replace(',', '')))
            except ValueError:
                pass


def unsupported_numbers(text: str, payload: dict) -> list[float]:
    """Numbers the agent stated that its payload does not support.

    A figure counts as supported if it matches a payload value once rounding is
    allowed for -- an agent quoting 1,000.6 psi as "1,001 psi" is reporting
    faithfully, not inventing. Anything left over was made up, which is the one
    thing these agents are not allowed to do.
    """
    allowed: set[float] = set()
    _payload_numbers(payload, allowed)
    # A rounded quote of an allowed value is still that value.
    allowed |= {round(v) for v in allowed} | {round(v, 1) for v in allowed}

    bad = []
    for match in _NUMBER.finditer(text):
        try:
            number = float(match.group().replace(',', ''))
        except ValueError:
            continue
        if number in _FREE_INTEGERS and number == int(number):
            continue
        tolerance = max(0.5, abs(number) * 0.01)
        if not any(abs(number - value) <= tolerance for value in allowed):
            bad.append(number)
    return bad


# --------------------------------------------------------------------------
# House style, applied after the fact
# --------------------------------------------------------------------------

_SPELLED_MONEY = re.compile(r'(?<![\w$])\$?([\d,]+(?:\.\d+)?)\s*(?:dollars|dollar|USD|usd)\b')
_BARE_THOUSANDS = re.compile(r'\$(\d{4,})')
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
_DIGITS = re.compile(r'\d+(?:\.\d+)?')

# The small model used for component agents reproduces payload field names
# verbatim however the prompt is worded, so they are translated here instead.
_FIELD_WORDS = [
    ('receive_flow_bpd', 'arriving flow'), ('baseline_water_bpd', 'usual water rate'),
    ('discharge_psi', 'discharge pressure'), ('pressure_psi', 'pressure'),
    ('water_bpd', 'barrels of water a day'), ('inflow_bpd', 'inflow'),
    ('flow_bpd', 'flow'), ('oil_bpd', 'barrels of oil a day'),
    ('gas_mcfd', 'mcf of gas a day'), ('level_pct', 'level'),
    ('status_code', 'status'), ('disposal_psi', 'disposal pressure'),
    ('water bpd', 'barrels of water a day'), ('oil bpd', 'barrels of oil a day'),
    ('flow bpd', 'flow'), ('discharge psi', 'discharge pressure'),
    ('disposal psi', 'disposal pressure'), ('pressure psi', 'pressure'),
    ('level pct', 'level'), ('inflow bpd', 'inflow'),
]


def _commas(number: str) -> str:
    cleaned = number.replace(',', '')
    try:
        return f'{int(round(float(cleaned))):,}'
    except ValueError:
        return number


def _tidy(text: str) -> str:
    """Put an agent's answer into the panel's house style.

    Small models will not hold a formatting rule consistently across a whole
    tree of calls -- the same model writes "$1,296" in one answer and "905
    dollars" in the next. Formatting is deterministic work, so it is done here
    rather than asked for repeatedly in the prompt. This never changes a value,
    only how it reads.
    """
    text = _SPELLED_MONEY.sub(lambda m: '$' + _commas(m.group(1)), text)
    text = _BARE_THOUSANDS.sub(lambda m: '$' + _commas(m.group(1)), text)
    for field, words in _FIELD_WORDS:
        text = re.sub(re.escape(field), words, text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\n\s*', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text).strip()

    # A model padding to a sentence quota repeats itself. Two tests catch it:
    # near-identical wording, and a sentence whose figures were all stated
    # already, which is the usual shape of an echo ("78% full" twice).
    kept, phrases, numbers = [], set(), set()
    for sentence in _SENTENCE_SPLIT.split(text):
        fingerprint = re.sub(r'[^a-z0-9]', '', sentence.lower())
        if not fingerprint:
            continue
        if any(fingerprint in other or other in fingerprint for other in phrases):
            continue
        found = set(_DIGITS.findall(sentence))
        if kept and found and found <= numbers:
            continue
        phrases.add(fingerprint)
        numbers |= found
        kept.append(sentence.strip())
    return ' '.join(kept)


# --------------------------------------------------------------------------
# Deterministic payloads -- the only facts an agent ever sees
# --------------------------------------------------------------------------

def _round(value, digits=2):
    return None if value is None else round(float(value), digits)


def _dollars(value):
    """Whole dollars. Operators do not act on cents, and a model handed 3858.62
    will faithfully reproduce "$3858.62" no matter how the prompt is worded."""
    return None if value is None else int(round(float(value)))


# Sensor readings carry noise, so a reading near its expected value is healthy.
# Without an explicit tolerance an agent reports 644.9 against a 650 baseline as
# a mismatch, which is noise dressed up as a finding.
NOISE_PCT = 3.0
NOISE_PSI = 15.0


def _off_by(actual, expected, tolerance_pct=NOISE_PCT):
    """Percent deviation, and whether it exceeds sensor noise."""
    if not expected:
        return 0.0, False
    delta = (actual - expected) / expected * 100.0
    return round(delta, 1), abs(delta) > tolerance_pct


def well_payload(data, facility: dict, well: dict, now: int) -> dict:
    """What one well's sensors recorded, plus what its production is worth."""
    status = int(data.value(well['id'], 'status', now, 1))
    water = data.value(well['id'], 'water_bpd', now)
    drift, abnormal = _off_by(water, well['baseline_water_bpd'])
    if status != 1:
        assessment = 'Shut in, so producing no water, oil or gas and earning nothing.'
    elif abnormal:
        assessment = (f'Producing {_round(water)} barrels of water a day, which is '
                      f'{drift:+.1f}% off its usual {well["baseline_water_bpd"]}.')
    else:
        assessment = (f'Producing normally at {_round(water)} barrels of water a day, '
                      f'in line with its usual {well["baseline_water_bpd"]}.')
    return {
        'asset_id': well['id'], 'kind': 'well',
        'producing': bool(status == 1),
        'status_code': status,
        'water_bpd': _round(water),
        'baseline_water_bpd': well['baseline_water_bpd'],
        'off_baseline_pct': drift,
        'oil_bpd': well['oil_bpd'],
        'gas_mcfd': well['gas_mcfd'],
        'revenue_per_hour_usd': _dollars(data.well_revenue_per_hour(well)),
        'assessment': assessment,
    }


def tank_payload(data, facility: dict, now: int) -> dict:
    """Level, capacity and how much room is left before the automatic shut-in."""
    tank = facility['tank']
    level = data.value(tank['id'], 'level_pct', now)
    capacity = tank['capacity_bbl']
    shutdown = data.limits['shutdown']
    warning = data.limits['warning']
    inflow = data.value(facility['id'], 'inflow_bpd', now)
    outflow = data.value(facility['pump']['id'], 'flow_bpd', now)
    direction = 'rising' if inflow > outflow else 'falling' if outflow > inflow else 'steady'
    band = ('past the shutdown limit' if level >= shutdown
            else 'above the warning limit' if level >= warning else 'below the warning limit')
    assessment = f'{_round(level)}% full and {direction}, {band}.'
    return {
        'asset_id': tank['id'], 'kind': 'tank',
        'level_pct': _round(level),
        'capacity_bbl': capacity,
        'volume_bbl': _round(capacity * level / 100.0),
        'warning_pct': data.limits['warning'],
        'shutdown_pct': shutdown,
        'headroom_bbl': _round(capacity * (shutdown - level) / 100.0),
        'inflow_bpd': _round(inflow),
        'pump_flow_bpd': _round(outflow),
        'net_fill_bpd': _round(inflow - outflow),
        'assessment': assessment,
    }


def pump_payload(data, facility: dict, now: int) -> dict:
    """Pump state against what the network says a healthy pump should show."""
    pump = facility['pump']
    disposal = data.system_of[facility['id']]['disposal_site']['pressure_psi']
    status = int(data.value(pump['id'], 'status', now))
    flow = data.value(pump['id'], 'flow_bpd', now)
    discharge = data.value(pump['id'], 'discharge_psi', now)
    expected = disposal + 150 if status == 1 else disposal
    if status == 2:
        assessment = ('Reporting a fault. It is moving no water, so the tank has no '
                      'outlet and discharge pressure has fallen to the bare disposal '
                      'pressure.')
    elif status == 0:
        assessment = 'Stopped normally between its setpoints. This is not a fault.'
    elif abs(discharge - expected) > NOISE_PSI:
        assessment = (f'Running, but discharge pressure is {_round(discharge - expected)} psi '
                      f'from the {expected} psi expected while running.')
    else:
        assessment = 'Running normally, flow and discharge pressure both as expected.'
    return {
        'asset_id': pump['id'], 'kind': 'pump',
        'status_code': status,
        'status_meaning': {0: 'stopped', 1: 'running', 2: 'fault'}.get(status, 'unknown'),
        'flow_bpd': _round(data.value(pump['id'], 'flow_bpd', now)),
        'max_flow_bpd': pump['max_flow_bpd'],
        'discharge_psi': _round(data.value(pump['id'], 'discharge_psi', now)),
        'disposal_psi': disposal,
        'expected_discharge_psi_running': disposal + 150,
        'expected_discharge_psi_stopped': disposal,
        'start_level_pct': pump['start_level_pct'],
        'stop_level_pct': pump['stop_level_pct'],
        'assessment': assessment,
    }


def pipeline_payload(data, facility: dict, now: int) -> dict:
    """What arrived at the disposal end, against what the pump claims it sent."""
    pipeline = facility['pipeline']
    pump = facility['pump']
    disposal = data.system_of[facility['id']]['disposal_site']['pressure_psi']
    sent = data.value(pump['id'], 'flow_bpd', now)
    received = data.value(pipeline['id'], 'receive_flow_bpd', now)
    pressure = data.value(pipeline['id'], 'pressure_psi', now)
    pumping = sent > 1.0
    expected = disposal + 50 if pumping else disposal
    loss, leaking = _off_by(received, sent) if pumping else (0.0, False)
    if not pumping:
        assessment = 'Idle. Nothing is being pumped into it, so it sits at disposal pressure.'
    elif leaking:
        assessment = (f'Carrying water, but {_round(sent - received)} bbl/day less arrives at '
                      f'disposal than the pump sent ({loss:+.1f}%).')
    elif abs(pressure - expected) > NOISE_PSI:
        assessment = f'Carrying water at {_round(pressure)} psi against {expected} psi expected.'
    else:
        assessment = 'Carrying water normally; what the pump sends is what arrives.'
    return {
        'asset_id': pipeline['id'], 'kind': 'pipeline',
        'receive_flow_bpd': _round(received),
        'pump_flow_bpd': _round(sent),
        'shortfall_bpd': _round(max(0.0, sent - received)),
        'pressure_psi': _round(data.value(pipeline['id'], 'pressure_psi', now)),
        'disposal_psi': disposal,
        'expected_pressure_psi_pumping': disposal + 50,
        'expected_pressure_psi_idle': disposal,
        'max_bpd': pipeline.get('max_bpd'),
        'max_pressure_psi': pipeline.get('max_pressure_psi'),
        'assessment': assessment,
    }


def component_payloads(data, facility: dict, now: int) -> list[dict]:
    """Every component of one facility, in the order the water flows."""
    payloads = [well_payload(data, facility, well, now) for well in facility['wells']]
    payloads.append(tank_payload(data, facility, now))
    payloads.append(pump_payload(data, facility, now))
    payloads.append(pipeline_payload(data, facility, now))
    return payloads


def facility_payload(view: dict, facility_id: str, components: list[dict]) -> dict:
    """The facility's own state plus whatever plan the engine already verified."""
    alert = next((a for a in view['alerts'] if a['facility_id'] == facility_id), None)
    snapshot = next((f for f in view['facilities'] if f['id'] == facility_id), None)
    payload = {
        'facility_id': facility_id,
        'component_count': len(components),
        'components': components,
        'has_active_incident': alert is not None,
    }
    if snapshot:
        payload['level_pct'] = _round(snapshot.get('level_pct'))
        payload['inflow_bpd'] = _round(snapshot.get('inflow_bpd'))
    if alert:
        plan = alert['recommendation']
        payload['incident'] = {
            'category': alert['category'],
            'hours_to_limit': alert.get('hours_to_limit'),
            'evidence': list(alert.get('evidence', [])),
            'confidence': alert.get('confidence'),
        }
        payload['verified_plan'] = {
            'label': plan['label'],
            'cost_usd': _dollars(plan['cost']),
            'do_nothing_cost_usd': _dollars(plan['baseline_cost']),
            'saving_usd': _dollars(plan['baseline_cost'] - plan['cost']),
            'trucks': plan.get('trucks', 0),
            'trips_per_truck': plan.get('trips_per_truck', 0),
            'rejected_alternatives': [
                {'label': alt['label'], 'cost_usd': _dollars(alt['cost'])}
                for alt in plan.get('alternatives', [])[:4]],
        }
    return payload


def system_payload(view: dict, data, system_id: str, facilities: list[dict]) -> dict:
    """The shared-resource picture: one fleet, one disposal site, many tanks."""
    ops = data.ops
    competing = [a for a in view['alerts']
                 if a['system_id'] == system_id and a['category'] == 'pump_failure']
    return {
        'system_id': system_id,
        'fleet_size': ops['systems'][system_id]['emergency_fleet_size'],
        'truck_capacity_bbl': ops['emergency_trucking']['truck_capacity_bbl'],
        'cost_per_trip_usd': _dollars(ops['emergency_trucking']['cost_per_trip']),
        'repair_hours': ops['expected_repair_hours']['pump_failure'],
        'disposal_site_id': next(s['disposal_site']['id'] for s in data.network['systems']
                                 if s['id'] == system_id),
        'tanks_filling_now': len(competing),
        'competing_facilities': [
            {'facility_id': a['facility_id'],
             'hours_to_limit': a.get('hours_to_limit'),
             'plan': a['recommendation']['label'],
             'cost_usd': _dollars(a['recommendation']['cost']),
             'trucks_assigned': a['recommendation'].get('trucks', 0)}
            for a in competing],
        'total_planned_cost_usd': _dollars(sum(a['recommendation']['cost'] for a in competing)),
        'total_do_nothing_cost_usd': _dollars(
            sum(a['recommendation']['baseline_cost'] for a in competing)),
        'facilities': facilities,
    }


# --------------------------------------------------------------------------
# Talking to the model
# --------------------------------------------------------------------------

ROLE_RULES = (
    'You brief night-shift oilfield operators. They are tired, they are reading '
    'on a small panel, and they need to act. Follow these rules exactly:\n'
    '1. Use ONLY numbers that appear in the JSON payload you are given. Never '
    'calculate a new figure and never estimate one.\n'
    '2. If something is not in the payload, say you do not have it.\n'
    '3. Write money as $905 or $3,106. Never write "905.0", "USD" or decimals '
    'on a dollar amount.\n'
    '4. Write times as "70 minutes" or "2.6 hours", and levels as "78% full".\n'
    '5. Name equipment the way the panel does: "the pump", "the tank", '
    '"Well C1". Use a full tag like S2_WELL_C1 only when naming which specific '
    'well to shut in.\n'
    '6. Plain sentences only. No markdown, no bullet characters, no headings, '
    'no jargon, no restating these rules.\n'
    '7. Start every sentence with a capital letter and end it with a full stop.\n'
    '8. Be brief. Never exceed the sentence limit you are given.'
)

PROMPTS = {
    'component': (
        'You report one piece of equipment. The payload "assessment" field holds '
        'the verified conclusion about it, and the "kind" field says what you '
        'are -- a well, a tank, a pump or a pipeline. Never call yourself any '
        'other kind of equipment, and never invent a name or tag for yourself: '
        'the panel already shows which asset this is, so begin with "This pump", '
        '"This tank", "This well" or "This pipeline". Say what is happening in '
        'one short sentence, then give the one or two readings that show it. '
        'Never contradict the assessment and never compare numbers yourself -- '
        'small differences are sensor noise and are already accounted for. Do '
        'not mention cost or what should be done. Two sentences maximum.'),
    'facility': (
        'You brief the operator on one facility. Write exactly three sentences, '
        'in this order and nothing else. First: the action to take and what it '
        'costs, starting with the word "Suggest". Second: why, in terms of what '
        'is physically happening at the equipment and what doing nothing would '
        'cost instead. Third: the next best option and its cost, so the operator '
        'can see the tradeoff. The plan was already computed and proven; explain '
        'it, never re-derive it.'),
    'system': (
        'You brief the operator on a whole system, where several tanks may be '
        'filling at once and all of them share one truck fleet. Write at most '
        'three sentences. First: how to split the trucks, starting with the word '
        '"Suggest", naming each facility and what it gets. Second: why that '
        'split, including how many trucks exist, how many tanks are filling, and '
        'the total cost against doing nothing. Third, only if it is true: say '
        'plainly that there are not enough trucks for every tank and that is why '
        'one of them is handled a different way.'),
}


async def _complete(client: httpx.AsyncClient, model: str, instruction: str,
                    payload: dict) -> str:
    """One model call, returning its prose or raising for the caller to handle."""
    response = await client.post(
        config.NVIDIA_URL,
        headers={'Authorization': f'Bearer {config.api_key()}'},
        json={'model': model,
              'messages': [{'role': 'system', 'content': ROLE_RULES},
                           {'role': 'user',
                            'content': f'{instruction}\n\nPAYLOAD:\n'
                                       f'{json.dumps(payload, default=str)}'}],
              # These models default to emitting a long hidden reasoning_content
              # before any answer, which costs 15x the latency and often leaves
              # nothing for content at all. The agents explain numbers that are
              # already computed and proven, so there is nothing to reason about.
              'chat_template_kwargs': {'thinking': False},
              'max_tokens': 700, 'temperature': 0.1},
        timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    message = response.json()['choices'][0]['message']
    return (message.get('content') or '').strip()


async def run_agent(client: httpx.AsyncClient, tier: str, model: str,
                    payload: dict) -> dict:
    """Run one agent, verify its numbers, and fall back rather than lie.

    A model that invents a figure gets one more attempt with the offending
    numbers named. If it still will not comply, the agent is reported as
    unverified with no prose at all -- the UI then shows the payload, which is
    the truth the prose was supposed to describe.
    """
    instruction = PROMPTS[tier]
    attempt_note = ''
    for attempt in range(MAX_ATTEMPTS):
        try:
            text = await _complete(client, model, instruction + attempt_note, payload)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            return {'tier': tier, 'text': '', 'verified': False,
                    'error': f'{type(exc).__name__}: {exc}'[:200]}
        if not text:
            attempt_note = '\n\nYou returned nothing. Answer in plain sentences.'
            continue
        invented = unsupported_numbers(text, payload)
        if not invented:
            return {'tier': tier, 'text': _tidy(text), 'verified': True}
        attempt_note = ('\n\nYour previous answer used numbers that are not in the '
                        f'payload: {invented}. Use only payload values.')
    return {'tier': tier, 'text': '', 'verified': False,
            'error': 'Agent could not answer using only payload values.'}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

async def analyse(analysis, view: dict, facility_id: str):
    """Walk the tree for one incident, yielding each agent's answer as it lands.

    Components first and in parallel, because they are independent and fast;
    then the facility agents that depend on them; then the system agent, which
    needs every facility's plan before it can talk about sharing trucks. The
    caller streams these, so the panel fills progressively instead of waiting
    for the slowest tier.
    """
    data = analysis.data
    system_id = data.system_of[facility_id]['id']
    siblings = [a['facility_id'] for a in view['alerts']
                if a['system_id'] == system_id and a['facility_id'] != facility_id]

    limiter = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient() as client:
        async def guarded(tier, model, payload):
            async with limiter:
                return await run_agent(client, tier, model, payload)

        # -- components of the facility that was clicked ---------------------
        facility = data.facilities[facility_id]
        payloads = component_payloads(data, facility, view['now'])
        tasks = [asyncio.create_task(guarded('component', config.component_model(), p))
                 for p in payloads]
        for payload, task in zip(payloads, tasks):
            result = await task
            yield {**result, 'asset_id': payload['asset_id'],
                   'kind': payload['kind'], 'payload': payload,
                   'facility_id': facility_id}

        components = [{'asset_id': p['asset_id'], 'kind': p['kind'], **p}
                      for p in payloads]

        # -- the facility itself, plus any sibling competing for the trucks --
        facility_jobs = {facility_id: facility_payload(view, facility_id, components)}
        for sibling in siblings:
            # Siblings are summarised without expanding their components: they
            # matter here only as competitors for the same fleet.
            facility_jobs[sibling] = facility_payload(view, sibling, [])

        running = {fid: asyncio.create_task(
            guarded('facility', config.reasoning_model(), payload))
            for fid, payload in facility_jobs.items()}
        facility_results = []
        for fid, task in running.items():
            result = await task
            facility_results.append({'facility_id': fid, **facility_jobs[fid]})
            yield {**result, 'facility_id': fid, 'payload': facility_jobs[fid]}

        # -- the system agent, once every facility's plan is known -----------
        payload = system_payload(view, data, system_id, facility_results)
        result = await guarded('system', config.reasoning_model(), payload)
        yield {**result, 'system_id': system_id, 'payload': payload}
