"""Regression: a run that stops early (MAX_PER_RUN / points) must resume where it stopped, not re-pay for items."""
import collections, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import test_flow as t                      # reuses the fake CJ/Shopify harness (and re-runs its own asserts)
app, S, STORE = t.app, t.S, t.STORE
STORE.clear(); S.update(cj_cap=10**9, cj_calls=0)
app.DAILY_POINTS, app.MAX_PER_RUN, app.PAGE_SIZE = 1000, 3, 50
seen = collections.Counter()
orig = app.cj_detail
app.cj_detail = lambda pid, ledger: (seen.update([pid]), orig(pid, ledger))[1]
for day in range(1, 5):
    app.run_sync()
    STORE["s"]["points"]["date"] = "2000-01-0%d" % day          # pretend a new day started
print("detail calls per product:", dict(seen))
assert seen and max(seen.values()) == 1, "an item was processed (and paid for) twice"
assert len(seen) == 12, len(seen)                                # 4 runs x MAX_PER_RUN 3, no repeats
print("RESUME TEST PASS; cursor:", STORE["s"]["cursor"])
