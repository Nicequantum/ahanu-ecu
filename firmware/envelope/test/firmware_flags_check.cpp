// Compiled with -fno-exceptions -fno-rtti to prove the header needs neither.
#include "envelope.h"

namespace {
grok_pilot::Envelope g_env{grok_pilot::EnvelopeConfig{}};  // static storage, no heap
}

int envelope_firmware_check(double now) {
  grok_pilot::Proposal p = {0, 0, 1, 1, 100.0, 101.0, now, 100, 1};
  return static_cast<int>(g_env.evaluate(p, now).decision);
}
