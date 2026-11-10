Fixtures in Tests/GrokPilotCoreTests/Fixtures are generated, not hand-written:
- sim-golden.json: Ahanu PR #4 `simPicture(...,"efi")` at t = 0, 1234, 987654, 1760000000000 ms
  (run from an Ahanu engine-dashboard checkout with `npx tsx`; see docs/IOS-PROTOTYPE.md).
- curriculum-vectors.json: `python3 ios/GrokPilotDash/tools/gen_curriculum_vectors.py` (from repo root),
  random streams through src/grok_pilot/curriculum.py.
- proposal-response.v1.schema.json: copy of src/grok_pilot/schemas/proposal-response.v1.schema.json.
