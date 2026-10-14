# Zero-Hardware Bench: Speeduino Teensy 4.1 + Ardu-Stim

Goal: compile the Speeduino firmware for Teensy 4.1, flash it, and drive it with a simulated crank/cam signal from Ardu-Stim. No engine required.

Legend: ✅ **verified** = run or read from the actual repo files on 2026-10-13. ⚠️ **unverified** = taken from docs or not yet tested on hardware.

## Bill of materials
- A Teensy 4.1 (bare), or the Speeduino Dropbear V2 (which has a Teensy 4.1 on board)
- An Arduino Nano (recommended by Ardu-Stim) or Uno
- 2 USB cables, jumper wires, optional 10k pot for RPM

## 1. Build Speeduino for Teensy 4.1 ✅

```bash
git clone --recurse-submodules https://github.com/Nicequantum/ahanu-ecu.git
cd ahanu-ecu
git submodule update --init --recursive          # if cloned without --recurse
python3 -m venv .piovenv && .piovenv/bin/pip install platformio
cd third_party/speeduino                          # pinned at tag 202501 (29bdaa3)
../../.piovenv/bin/pio run -e teensy41
```
✅ We verified this on Linux on 2026-10-13. The build reported `SUCCESS`, FLASH code 232256 bytes, and wrote `.pio/build/teensy41/firmware.hex`.
Note: upstream `default_envs = megaatmega2560`. You **must** pass `-e teensy41`. The env name was checked in `third_party/speeduino/platformio.ini`.

## 2. Flash the Teensy

**Option A: PlatformIO direct** ⚠️ (not yet run against a physical board)
```bash
../../.piovenv/bin/pio run -e teensy41 -t upload
```
On Linux, install the Teensy udev rules first (https://www.pjrc.com/teensy/00-teensy.rules).

**Option B: SpeedyLoader** ⚠️ (UI flow comes from the Speeduino docs and hasn't been tested by us)
1. Download SpeedyLoader: https://github.com/speeduino/SpeedyLoader/releases
2. Plug in the Teensy over USB. Pick the port, pick a firmware version, and pick the **Teensy 4.1** board. SpeedyLoader downloads official release builds and uses the Teensy loader. Upstream release `202501` matches our pin.
3. Custom `.hex` (our builds): use the PJRC Teensy Loader (`teensy_loader_cli --mcu=TEENSY41 -w -v .pio/build/teensy41/firmware.hex`). ⚠️ We haven't confirmed whether SpeedyLoader accepts local hex files.

## 3. Build and flash Ardu-Stim ✅ (build only)

Easiest path: the Ardu-Stim GUI (https://github.com/speeduino/Ardu-Stim/releases/latest) has an "upload firmware" button. It works for the **Nano only**.

From source:
```bash
git clone https://github.com/speeduino/Ardu-Stim.git
cd Ardu-Stim/ardustim            # contains platformio.ini (envs: nano, uno, diecimilaatmega328)
pio run -e nano                  # ✅ builds (verified 2026-10-13)
pio run -e nano -t upload        # ⚠️ not run against hardware
# Uno: pio run -e uno -t upload
```

## 4. Wiring

Ardu-Stim outputs, from the Ardu-Stim README ✅:
- Nano/Uno **D8** = crank (primary), **D9** = cam (secondary), **D10** = 2nd cam; optional pot wiper on **A0** for RPM

Speeduino trigger inputs for pin layout **Dropbear (board layout 55)** on `CORE_TEENSY41`, from `speeduino/init.cpp` ✅:
- `pinTrigger = 20` (crank / CAS), `pinTrigger2 = 21` (cam). These are **Teensy pin numbers**.

| Ardu-Stim | Teensy 4.1 / Dropbear |
|---|---|
| D8 (crank) | Teensy pin 20 (Dropbear: crank trigger input) |
| D9 (cam) | Teensy pin 21 (Dropbear: cam trigger input) |
| GND | GND (**common ground required**) |

⚠️ **Voltage warning:** the Nano/Uno output is 5 V and the Teensy 4.1 is **3.3 V only, not 5 V tolerant**. On a **bare Teensy** you need a divider or level shifter on each line, e.g. 10k/20k. On the **Dropbear**, feed the board's crank/cam connector pins, which go through the board's trigger conditioning. The exact Dropbear connector pin numbers are ⚠️ **unverified**; check the Dropbear V2 pinout docs.

## 5. Configure and verify in TunerStudio

1. Install TunerStudio MS (https://www.tunerstudio.com). Create a project and load the firmware's INI: `third_party/speeduino/reference/speeduino.ini` ✅ (file exists at the pin).
2. Connect over the Teensy USB serial port. Settings: pin layout = **Dropbear**, and the trigger pattern has to match Ardu-Stim's (e.g. both **Missing Tooth 36-1** ⚠️, the GM 350/HEI real-engine pattern is TBD).
3. Burn, power-cycle, and set Ardu-Stim to e.g. 1000 RPM fixed.
4. **Pass criteria:** TunerStudio's RPM gauge tracks the Ardu-Stim RPM within ±1 %, sweep 500→6000 shows no sync loss (watch the "sync loss" counter), and the SD log or TunerStudio log records RPM.

Serial sanity check without TunerStudio ⚠️ (based on the legacy Speeduino serial protocol, not yet tested by us):
```bash
pio device monitor -b 115200   # then type 'Q' → firmware signature string
```

## 6. Next steps once the loop works
- Capture a TunerStudio log and map its fields to `docs/DATA-SCHEMA.md` to see which fields are missing from stock firmware.
- Add a simulated wideband (a serial AFR feed) to exercise the validation envelope.
