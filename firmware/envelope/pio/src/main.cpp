// Teensy 4.1 smoke build: proves envelope.h compiles with the ARM toolchain
// (no heap, exceptions or RTTI). It isn't a firmware image for the engine.
#include <Arduino.h>
#include "envelope.h"

static grok_pilot::Envelope g_env{grok_pilot::EnvelopeConfig{}};

void setup() {
  Serial.begin(115200);
  g_env.set_cell(grok_pilot::Table::VE, 5, 5, 100.0);
}

void loop() {
  double now = millis() / 1000.0;
  grok_pilot::Proposal p = {0, 0, 5, 5, 100.0, 103.0, now, 100, 1};
  grok_pilot::Result r = g_env.evaluate(p, now, nullptr, nullptr, false);
  Serial.println(grok_pilot::reason_name(r.reason));
  delay(1000);
}
