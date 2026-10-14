## REQUEST
request_id: {request_id}
engine_id: {engine_id} ({engine_label})
stage: {stage}
status: {status}
engine_room_mode: {engine_room_mode}
allowed_rpm_idx: {allowed_rpm_idx}
allowed_tables: {allowed_tables}
max_proposals: {max_proposals}
wideband_fault_afr: {wideband_fault_afr}

## ENVELOPE LIMITS
{envelope_json}

## CARB / JETTING (null in efi mode)
{carb_json}

## ENGINE STATE (latest sample per engine)
{engine_state_json}

## TABLE CELLS (current values, target engine, cells with recent activity)
{tables_json}

## RECENT AUDIT TRAIL (newest last; target engine)
{audit_json}

## RECENT HISTORY ({history_note})
{history_json}

## RESPONSE
Return ONLY a JSON object that validates against "grok-pilot.proposal-response.v2".
