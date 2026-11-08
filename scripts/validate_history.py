"""Offline scoring only: labels are never passed to the runtime engine."""
import json
from backend.engine import Dataset, ROOT

data=Dataset('history/full_week')
labels=json.loads((ROOT/'history/full_week/answer_key.json').read_text())
detected=0
for event in labels:
    # Measure detection during the incident, not before gradual evidence is visible.
    at=event['onset_unix']+int((event['end_unix']-event['onset_unix'])*.75)//300*300
    result=data.analyze(at)
    match=next((a for a in result['alerts'] if a['facility_id']==event['facility'] and a['category']==event['category']),None)
    detected+=bool(match)
    print(event['id'],event['category'],'DETECTED' if match else 'MISSED',match['recommendation']['label'] if match else '')
print(f'Detected {detected}/{len(labels)} labeled incidents at 75% of their duration. This is not a full precision/recall evaluation.')
