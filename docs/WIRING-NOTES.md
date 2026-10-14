# Wiring Notes (pre-hardware)

Status: design notes only. Nothing has been built or measured. Verify every value against the datasheets before wiring.

## Wideband UART (Spartan 3 Lite v2 → Teensy 4.1) — ⚠️ PENDING HARDWARE CHANGE

The brief specifies Spartan 3 Lite v2 serial output at 9600 baud with 5 V logic (⚠️ the 5 V level is unverified against the 14Point7 docs). The Teensy 4.1 runs 3.3 V logic, its pins are **not 5 V tolerant**, and the absolute maximum is about 3.6 V. So the Spartan TX line needs a divider into the Teensy RX.

| Divider (top / bottom) | V_out from 5 V | Verdict |
|---|---|---|
| ~~10k / 2k~~ (previous spec) | 5 × 2/12 ≈ **0.83 V** | ❌ Below a logic-HIGH threshold, so the UART won't read. **Replaced.** |
| **10k top / 20k bottom** | 5 × 20/30 ≈ **3.33 V** | ✅ New spec. Use 1 % resistors: the worst case at 5.25 V supply is ≈ 3.5 V, still under the 3.6 V maximum |

Wiring: Spartan TX → 10k → node → Teensy RX; node → 20k → GND. Spartan GND goes to Teensy GND (common ground, referenced at the sensor ground). Teensy TX → Spartan RX only if commands are needed. A 3.3 V output is normally read fine by 5 V input, but that's ⚠️ unverified for the Spartan.
- **Alternative:** a dedicated level shifter, such as a 74LVC1T45 or a 74LVC245 powered at 3.3 V with 5 V-tolerant inputs.
- **Speed:** a 30k-total divider is fine at 9600 baud. At much higher baud rates, RC edges with pin capacitance would need checking.
- **Which Teensy UART:** the Dropbear breaks out `Serial1` as the secondary serial header (`init.cpp`), but the wideband B location is still undecided (#4).

**Status:** documentation updated 2026-10-13. Any already-built harness that uses 10k/2k has to be changed. See issue #4.

## Ardu-Stim → bare Teensy
See [ARDU-STIM-BENCH.md](ARDU-STIM-BENCH.md). It uses the same 5 V → 3.3 V concern and the same 10k/20k divider.
