from conftest import FakeDepth, FakeFlow, fake_models

from walksafe.perception.loader import warm_up


def test_warm_up_runs_each_model_twice_and_reports_timings():
    depth, flow = FakeDepth(), FakeFlow()
    timings = warm_up(fake_models(depth=depth, flow=flow))
    assert depth.calls == 2 and flow.calls == 2
    assert set(timings) == {f"{m}_{a}_ms" for m in ("depth", "detection", "flow") for a in ("first", "warm")}
