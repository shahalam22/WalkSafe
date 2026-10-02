from walksafe.config import CFG, load


def test_defaults_match_the_prototype_values():
    assert CFG.models.yolo_conf == 0.35
    assert CFG.models.depth_every_n_frames == 5
    assert CFG.camera.resize_width == 518
    assert CFG.agents.ttc_emergency == 1.0
    assert CFG.openings.min_width_px == 50


def test_yaml_override_changes_only_the_named_value(tmp_path):
    path = tmp_path / "exp.yaml"
    path.write_text("agents:\n  ttc_emergency: 1.5\n")
    cfg = load(str(path))
    assert cfg.agents.ttc_emergency == 1.5
    assert cfg.agents.ttc_critical == CFG.agents.ttc_critical
    assert cfg.models == CFG.models


def test_no_override_without_a_path(monkeypatch):
    monkeypatch.delenv("WALKSAFE_CONFIG", raising=False)
    assert load() == CFG
