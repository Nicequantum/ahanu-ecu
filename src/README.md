# src/

Firmware source goes here once the Speeduino fork is in place.

Planned layout:

- `speeduino/` — vendored or submodule of the Speeduino fork
- `custom/` — marine-specific tweaks and the AI self-tuning loop
- `gateway/` — serial-to-Ahanu bridge (or separate small Python project)
- `contracts/` — copies of Ahanu's EngineReading types for compile-time checking
