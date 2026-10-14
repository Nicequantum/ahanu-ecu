#pragma once
// EngineReading contract — mirrors Nicequantum/Ahanu src/lib/ahanu/types.ts
// and src/lib/ahanu/engine/*.ts. Both repos import from this shape.
// Any change here must be mirrored in Ahanu's types.ts in the same PR.

#include <Arduino.h>
#include <time.h>

// Bank on a twin-inboard boat. 'unmapped' is never a guess for port.
enum class EngineId : uint8_t { Port, Starboard, Unmapped };

// Where a normalized reading came from. Wire units never appear here.
enum class EngineSourceKind : uint8_t {
  AnalogN2K,   // "analog-n2k"
  SmartCraft,  // "smartcraft"
  Mefi,        // "mefi"
  Standalone,  // "standalone" — Speeduino / RusEFI / custom ECU
  Sim          // "sim"
};

enum class ReadingQuality : uint8_t { Ok, Stale, Missing };

// Carbureted analog today, EFI when a gateway is actually connected.
enum class EngineRoomMode : uint8_t { Carb, Efi };

// Opt-in live path. 'sim' is the only default.
enum class EngineFeed : uint8_t { Sim, Analog, Digital };

// One gauge sample. Gauges bind to this and nothing raw.
// 'unit' is the display unit after ingest conversion.
struct EngineReading {
  EngineId engineId;          // port | starboard | unmapped
  const char* param;          // e.g. "rpm", "coolantTempC", "oilPsi", "afr"
  float value;                // numeric value in wire units before conversion
  const char* unit;           // display unit, e.g. "RPM", "C", "psi", "AFR"
  time_t ts;                  // epoch seconds
  EngineSourceKind source;
  ReadingQuality quality;
  uint8_t instance;           // optional NMEA 2000 instance
  uint32_t pgn;               // optional source PGN

  // JSON shape expected by Ahanu's UDP JSON / TCP 39150 ingest:
  // {"engineId":"port","param":"rpm","value":2400,"unit":"RPM",
  //  "ts":"2026-10-13T21:48:00Z","source":"standalone","quality":"ok"}
};

// Tier 1 = discrete-status bit. Tier 2 = ECM DTC. Never the same object.
struct EngineAlarm {
  uint8_t tier;               // 1 or 2
  EngineId engineId;
  uint8_t instance;
  const char* code;
  const char* description;
  const char* state;          // "active" | "historic" | "unavailable"
  time_t ts;
  EngineSourceKind source;
  uint32_t pgn;
};

// Factory ECM code. Empty until a real EFI source connects.
struct EngineDtc {
  const char* code;
  const char* description;
  const char* state;          // "active" | "historic"
};