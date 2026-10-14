# Three-Tier Architecture

## Overview

Grok Pilot is a three-tier system. Each tier has a distinct role, and the tiers communicate through documented interfaces rather than shared code.

## Tier 1: Teensy 4.1 (Real-Time ECU)

- Runs Speeduino firmware with the marine layer (NMEA 2000 PGN publisher, dual-engine support)
- Owns the hard real-time loop: fuel, spark, injector drivers, ignition pre-drivers
- Enforces the fixed safety envelope: max fuel delta per cell, max spark advance delta, AFR floor and ceiling, lean cutoff
- The lean cutoff lives in hardware (comparator on the wideband), bypassing software entirely
- Never waits on the AI for a safety-critical decision
- Publishes normalized EngineReading objects to Ahanu over UDP JSON / TCP 39150

## Tier 2: iPhone 17 Pro Max / Mini (Consumer Product)

- Quantized model for the strategic layer: stage progression, plain-language explanations, anomaly flagging
- The interface and judgment layer, not the engine
- Strictly advisory for v1: the phone proposes, the Teensy disposes
- Every proposal is logged to the audit trail (timestamp, proposed value, accepted value, reasoning)
- Affordable entry point for the general public

## Tier 3: Mac Studio M5 Ultra, 512 GB (Development and Heavy Reasoning)

- Full-size model with unified memory for cross-engine correlation
- Runs the cloud-side Grok integration during testing
- Trains and validates the curriculum logic: cold-start enrichment, warm-up, hot idle, load-test stages
- Cross-correlates port and starboard data across months and years of logged runs
- The source of learned models that get quantized and deployed to Tier 2
- Where new tuning software and services for the general public are developed

## Data Flow

1. Teensy logs raw sensor data and publishes EngineReading objects
2. Tier 3 ingests the stream, reasons over it, and produces learned model updates
3. Learned models are quantized and pushed to Tier 2
4. Tier 2 runs the strategic layer and surfaces proposals to the operator
5. Tier 1 validates every proposal against the fixed envelope before applying

## The Edge

No open-source or commercial ECU today learns a model from engine tuning data. Manufacturers use AI for driver assistance, not physical engine tuning. Grok Pilot's differentiator is a live model that accumulates months and years of real-world data across twin engines and turns that into better tuning services for the general public.

## Open Decisions

- Whether the AI loop's slow strategic layer runs on Tier 2, Tier 3, or both
- Whether Grok does on-device inference (Tier 2) or cloud-assisted reasoning (Tier 3)
- How the curriculum state machine advances stages without human approval
- Dual-wideband disagreement handling as a first-class feature