// Mirrors tests/test_envelope.py (typed cases). Python-only cases (bool/str/None
// types) can't be expressed in C++'s typed API; the gateway's JSON decode handles those.
#include <gtest/gtest.h>
#include <math.h>
#include <limits>

#include "envelope.h"

using namespace grok_pilot;

namespace {
const double NOW = 1000.0;
const double INF_ = std::numeric_limits<double>::infinity();
const double NAN_ = std::numeric_limits<double>::quiet_NaN();

struct Fx {
  Envelope e;
  explicit Fx(EnvelopeConfig c = EnvelopeConfig()) : e(c) {
    for (int r = 0; r < 16; ++r)
      for (int m = 0; m < 16; ++m) {
        e.set_cell(Table::VE, r, m, 100.0);
        e.set_cell(Table::SPARK, r, m, 20.0);
        e.set_cell(Table::AFR_TARGET, r, m, 14.7);
      }
  }
};

EnvelopeConfig cfg(bool clamp = true) { EnvelopeConfig c; c.clamp_deltas = clamp; return c; }

Proposal P(int table, double before, double prop, double ts = NOW, int n = 100, int eng = 0, int r = 5, int m = 5) {
  Proposal p = {eng, table, r, m, before, prop, ts, n, 0};
  return p;
}
const int VE = 0, SP = 1, AFR = 2;
}  // namespace

TEST(Envelope, AcceptWithinLimits) {
  Fx f;
  Result r = f.e.evaluate(P(VE, 100, 103), NOW);
  EXPECT_EQ(r.decision, Decision::ACCEPTED);
  EXPECT_EQ(r.value_accepted, 103.0);
}

TEST(Envelope, FuelDeltaExactBoundaryAccepted) {
  for (double v : {105.0, 95.0}) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, v), NOW).decision, Decision::ACCEPTED) << v; }
}

TEST(Envelope, FuelDeltaOverIsClamped) {
  const double cases[][2] = {{105.0001, 105.0}, {94.9, 95.0}, {140.0, 105.0}};
  for (auto& c : cases) {
    Fx f;
    Result r = f.e.evaluate(P(VE, 100, c[0]), NOW);
    EXPECT_EQ(r.decision, Decision::CLAMPED);
    EXPECT_EQ(r.reason, Reason::FUEL_DELTA_EXCEEDED);
    EXPECT_NEAR(r.value_accepted, c[1], 1e-12);
  }
}

TEST(Envelope, FuelDeltaRejectMode) {
  Fx f(cfg(false));
  Result r = f.e.evaluate(P(VE, 100, 106), NOW);
  EXPECT_EQ(r.decision, Decision::REJECTED);
  EXPECT_EQ(r.reason, Reason::FUEL_DELTA_EXCEEDED);
}

TEST(Envelope, SparkDeltaBoundary) {
  struct { double v; Decision d; } cases[] = {{22.0, Decision::ACCEPTED}, {18.0, Decision::ACCEPTED},
                                             {22.01, Decision::CLAMPED}, {17.0, Decision::CLAMPED}};
  for (auto& c : cases) {
    Fx f;
    Result r = f.e.evaluate(P(SP, 20, c.v), NOW);
    EXPECT_EQ(r.decision, c.d) << c.v;
    EXPECT_GE(r.value_accepted, 18.0);
    EXPECT_LE(r.value_accepted, 22.0);
  }
}

TEST(Envelope, SparkAbsoluteLimits) {
  { Fx f; f.e.set_cell(Table::SPARK, 5, 5, 1.0); EXPECT_EQ(f.e.evaluate(P(SP, 1.0, -0.1), NOW).reason, Reason::SPARK_LIMIT); }
  { Fx f; f.e.set_cell(Table::SPARK, 5, 5, 35.0); EXPECT_EQ(f.e.evaluate(P(SP, 35.0, 36.01), NOW).reason, Reason::SPARK_LIMIT); }
  { Fx f; f.e.set_cell(Table::SPARK, 5, 5, 35.0); EXPECT_EQ(f.e.evaluate(P(SP, 35.0, 36.0), NOW).decision, Decision::ACCEPTED); }
}

TEST(Envelope, AfrFloorCeiling) {
  struct { double v; Decision d; Reason r; } cases[] = {
      {10.5, Decision::ACCEPTED, Reason::NONE}, {16.0, Decision::ACCEPTED, Reason::NONE},
      {10.49, Decision::REJECTED, Reason::AFR_FLOOR}, {16.01, Decision::REJECTED, Reason::AFR_CEILING},
      {0.0, Decision::REJECTED, Reason::AFR_FLOOR}, {-14.7, Decision::REJECTED, Reason::AFR_FLOOR}};
  for (auto& c : cases) {
    Fx f;
    Result r = f.e.evaluate(P(AFR, 14.7, c.v), NOW);
    EXPECT_EQ(r.decision, c.d) << c.v;
    EXPECT_EQ(r.reason, c.r) << c.v;
  }
}

TEST(Envelope, VeAbsoluteLimits) {
  for (double v : {9.99, 150.01, -5.0, 0.0}) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, v), NOW).reason, Reason::VE_LIMIT) << v; }
}

TEST(Envelope, NonFiniteRejected) {
  struct { double b, v, ts; } cases[] = {{100, NAN_, NOW}, {100, INF_, NOW}, {100, -INF_, NOW},
                                         {NAN_, 101, NOW}, {100, 101, NAN_}, {100, 101, INF_}};
  for (auto& c : cases) {
    Fx f;
    Result r = f.e.evaluate(P(VE, c.b, c.v, c.ts), NOW);
    EXPECT_EQ(r.decision, Decision::REJECTED);
    EXPECT_EQ(r.reason, Reason::INVALID_VALUE);
  }
  Fx f;
  EXPECT_TRUE(isnan(f.e.evaluate(P(VE, NAN_, 101), NOW).value_before));
}

TEST(Envelope, HugeValuesRejectedNotClamped) {
  Fx f;
  for (double v : {1e308, -1e308, 9223372036854775808.0}) {
    Result r = f.e.evaluate(P(VE, 100, v), NOW);
    EXPECT_EQ(r.reason, Reason::VE_LIMIT);
  }
  double cur = 0;
  ASSERT_TRUE(f.e.get_cell(Table::VE, 5, 5, &cur));
  EXPECT_EQ(cur, 100.0);
}

TEST(Envelope, NowNanRejected) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101), NAN_).reason, Reason::INVALID_VALUE); }

TEST(Envelope, OffTable) {
  int cases[][2] = {{-1, 0}, {0, -1}, {16, 0}, {0, 16}, {1000000000, 0}};
  for (auto& c : cases) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, NOW, 100, 0, c[0], c[1]), NOW).reason, Reason::OFF_TABLE); }
  Fx f;
  EXPECT_EQ(f.e.evaluate(P(3, 1, 1), NOW).reason, Reason::OFF_TABLE);
  EXPECT_EQ(f.e.evaluate(P(-1, 1, 1), NOW).reason, Reason::OFF_TABLE);
}

TEST(Envelope, WrongEngine) {
  for (int e : {1, -1, 2}) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, NOW, 100, e), NOW).reason, Reason::WRONG_ENGINE); }
}

TEST(Envelope, StaleOrFutureTimestamp) {
  for (double ts : {NOW - 2.0001, NOW - 3600, 0.0, NOW + 0.5001, NOW + 1e9}) {
    Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, ts), NOW).reason, Reason::STALE_TIMESTAMP) << ts;
  }
  for (double ts : {NOW - 2.0, NOW + 0.5}) {
    Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, ts), NOW).decision, Decision::ACCEPTED) << ts;
  }
}

TEST(Envelope, ReplayRejected) {
  Fx f;
  EXPECT_TRUE(f.e.evaluate(P(VE, 100, 101), NOW).applied());
  EXPECT_EQ(f.e.evaluate(P(VE, 101, 102), NOW).reason, Reason::STALE_TIMESTAMP);
}

TEST(Envelope, StaleBasisRejected) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 90, 92), NOW).reason, Reason::STALE_BASIS); }

TEST(Envelope, EvidenceBoundary) {
  struct { int n; bool ok; } cases[] = {{49, false}, {50, true}, {-1, false}};
  for (auto& c : cases) { Fx f; EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, NOW, c.n), NOW).applied(), c.ok) << c.n; }
  Fx f;
  EXPECT_EQ(f.e.evaluate(P(VE, 100, 101, NOW, -1), NOW).reason, Reason::INVALID_VALUE);
}

TEST(Envelope, FrozenRejects) {
  Fx f; f.e.frozen = true;
  EXPECT_EQ(f.e.evaluate(P(VE, 100, 101), NOW).reason, Reason::LEARNING_FROZEN);
}

static bool r_lt5(void*, int32_t, int32_t r, int32_t) { return r < 5; }
TEST(Envelope, StageLock) {
  Fx f;
  EXPECT_EQ(f.e.evaluate(P(VE, 100, 101), NOW, r_lt5, nullptr).reason, Reason::STAGE_LOCKED);
}

TEST(Envelope, RateLimitAndWindowBoundary) {
  Fx f;
  double v = 100.0;
  for (int k = 0; k < 3; ++k) {
    Result r = f.e.evaluate(P(VE, v, v + 1, NOW + k), NOW + k);
    ASSERT_TRUE(r.applied());
    v = r.value_accepted;
  }
  EXPECT_EQ(f.e.evaluate(P(VE, v, v + 1, NOW + 3), NOW + 3).reason, Reason::RATE_LIMITED);
  EXPECT_TRUE(f.e.evaluate(P(VE, v, v + 1, NOW + 60), NOW + 60).applied());
}

TEST(Envelope, RateLimitIsPerCell) {
  Fx f;
  for (int k = 0; k < 3; ++k) f.e.evaluate(P(VE, 100.0 + k, 101.0 + k, NOW + k), NOW + k);
  EXPECT_TRUE(f.e.evaluate(P(VE, 100, 101, NOW + 3, 100, 0, 6, 5), NOW + 3).applied());
}

TEST(Envelope, RejectionsDoNotMutateOrConsumeBudget) {
  Fx f;
  for (int k = 0; k < 10; ++k) f.e.evaluate(P(VE, 100, NAN_, NOW + k), NOW + k);
  double cur = 0;
  f.e.get_cell(Table::VE, 5, 5, &cur);
  EXPECT_EQ(cur, 100.0);
  EXPECT_TRUE(f.e.evaluate(P(VE, 100, 101, NOW + 10), NOW + 10).applied());
}

TEST(Envelope, RatchetBoundedByRateLimit) {
  Fx f;
  double v = 100.0;
  for (int k = 0; k < 100; ++k) {
    double t = NOW + k * 0.5;
    Result r = f.e.evaluate(P(VE, v, v * 10, t), t);
    if (r.applied()) v = r.value_accepted;
  }
  EXPECT_LE(v, 100.0 * pow(1.05, 4) + 1e-6);
}

TEST(Envelope, Determinism) {
  Fx a, b;
  double vals[] = {101, 130, NAN_, 99};
  for (int i = 0; i < 4; ++i) {
    Result ra = a.e.evaluate(P(VE, i == 0 ? 100 : NAN_, vals[i], NOW + i), NOW + i);
    Result rb = b.e.evaluate(P(VE, i == 0 ? 100 : NAN_, vals[i], NOW + i), NOW + i);
    EXPECT_EQ(ra.decision, rb.decision);
    EXPECT_EQ(ra.reason, rb.reason);
  }
}

TEST(Envelope, CommitFalseIsDryRun) {
  Fx f;
  f.e.evaluate(P(VE, 100, 104), NOW, nullptr, nullptr, false);
  double cur = 0;
  f.e.get_cell(Table::VE, 5, 5, &cur);
  EXPECT_EQ(cur, 100.0);
}

TEST(Envelope, ConfigOkGuardsFixedState) {
  EnvelopeConfig c; EXPECT_TRUE(Envelope(c).config_ok());
  c.rate_limit_touches = kMaxRateTouches + 1; EXPECT_FALSE(Envelope(c).config_ok());
  c.rate_limit_touches = 3; c.rpm_bins = 17; EXPECT_FALSE(Envelope(c).config_ok());
}

TEST(Envelope, ReasonNamesMatchSchema) {
  EXPECT_STREQ(reason_name(Reason::STALE_BASIS), "stale_basis");
  EXPECT_STREQ(reason_name(Reason::LEARNING_FROZEN), "learning_frozen");
  EXPECT_STREQ(decision_name(Decision::CLAMPED), "clamped");
}
