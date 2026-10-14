# contracts/

Shared interface between this ECU firmware and the Ahanu dashboard.

## engine_reading.h

C++ mirror of Ahanu's TypeScript types in `src/lib/ahanu/types.ts`:

- `EngineId` — port | starboard | unmapped
- `EngineSourceKind` — analog-n2k | smartcraft | mefi | standalone | sim
- `ReadingQuality` — ok | stale | missing
- `EngineRoomMode` — carb | efi
- `EngineFeed` — sim | analog | digital
- `EngineReading` — one gauge sample; gauges bind to this and nothing raw
- `EngineAlarm` — tier 1 discrete bit or tier 2 ECM DTC
- `EngineDtc` — factory ECM code

## Rules

1. Any field added or renamed here must be added or renamed in Ahanu's `types.ts` in the same pull request.
2. The JSON shape documented in the `EngineReading` comment is what the gateway publishes to Ahanu's UDP JSON or TCP 39150 path.
3. `unit` is always the display unit after ingest conversion — wire units never appear in `EngineReading`.
4. `source: "standalone"` is the slot for this ECU. Ahanu's `EngineSourceKind` already includes it.

## Cross-repo tracking

See the linked issue in Nicequantum/Ahanu for the integration checklist.