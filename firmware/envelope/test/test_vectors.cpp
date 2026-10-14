// Cross-check: replay Python-generated vectors through the C++ envelope and
// require identical decision, reason and values (bit-exact, NaN == NaN).
#include <gtest/gtest.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <memory>
#include <string>

#include "envelope.h"

using namespace grok_pilot;

namespace {
struct Allow { int lo, hi; };
bool allow_fn(void* ctx, int32_t, int32_t r, int32_t) {
  const Allow* a = static_cast<const Allow*>(ctx);
  return a->lo <= r && r <= a->hi;
}
bool same(double a, double b) { return (isnan(a) && isnan(b)) || a == b; }
}  // namespace

TEST(Vectors, PythonAndCppAgree) {
  FILE* fp = fopen(ENVELOPE_VECTORS_PATH, "r");
  ASSERT_NE(fp, nullptr) << ENVELOPE_VECTORS_PATH;
  std::unique_ptr<Envelope> env;
  char line[1024], name[256] = "";
  int steps = 0, mismatches = 0, lineno = 0;
  while (fgets(line, sizeof line, fp)) {
    ++lineno;
    if (line[0] == '#' || line[0] == '\n') continue;
    char tag = line[0];
    if (tag == 'S') {
      int eng, clamp;
      ASSERT_EQ(sscanf(line, "S %255s %d %d", name, &eng, &clamp), 3) << lineno;
      EnvelopeConfig c;
      c.engine_id = eng;
      c.clamp_deltas = clamp != 0;
      env.reset(new Envelope(c));
    } else if (tag == 'F') {
      char a[64], b[64], d[64];
      ASSERT_EQ(sscanf(line, "F %63s %63s %63s", a, b, d), 3);
      for (int r = 0; r < 16; ++r)
        for (int m = 0; m < 16; ++m) {
          env->set_cell(Table::VE, r, m, strtod(a, nullptr));
          env->set_cell(Table::SPARK, r, m, strtod(b, nullptr));
          env->set_cell(Table::AFR_TARGET, r, m, strtod(d, nullptr));
        }
    } else if (tag == 'C') {
      int t, r, m; char v[64];
      ASSERT_EQ(sscanf(line, "C %d %d %d %63s", &t, &r, &m, v), 4);
      env->set_cell(static_cast<Table>(t), r, m, strtod(v, nullptr));
    } else if (tag == 'Z') {
      int z; ASSERT_EQ(sscanf(line, "Z %d", &z), 1);
      env->frozen = z != 0;
    } else if (tag == 'P') {
      int eng, tc, r, m, n, lo, hi, commit;
      char sb[64], sp[64], sts[64], snow[64], dec[32], rea[32], svb[64], sva[64];
      ASSERT_EQ(sscanf(line, "P %d %d %d %d %63s %63s %63s %d %63s %d %d %d = %31s %31s %63s %63s", &eng, &tc, &r, &m,
                       sb, sp, sts, &n, snow, &lo, &hi, &commit, dec, rea, svb, sva), 16) << lineno;
      Proposal p = {eng, tc, r, m, strtod(sb, nullptr), strtod(sp, nullptr), strtod(sts, nullptr), n, 0};
      Allow a = {lo, hi};
      Result res = env->evaluate(p, strtod(snow, nullptr), lo >= 0 ? allow_fn : nullptr, &a, commit != 0);
      ++steps;
      bool ok = strcmp(decision_name(res.decision), dec) == 0 && strcmp(reason_name(res.reason), rea) == 0 &&
                same(res.value_before, strtod(svb, nullptr)) && same(res.value_accepted, strtod(sva, nullptr));
      if (!ok) {
        ++mismatches;
        if (mismatches <= 20)
          ADD_FAILURE() << "line " << lineno << " [" << name << "] python=" << dec << "/" << rea << "/" << sva
                        << " cpp=" << decision_name(res.decision) << "/" << reason_name(res.reason) << "/"
                        << res.value_accepted;
      }
    }
  }
  fclose(fp);
  EXPECT_GT(steps, 1000);
  EXPECT_EQ(mismatches, 0);
  printf("[vectors] %d steps replayed, %d mismatches\n", steps, mismatches);
}
