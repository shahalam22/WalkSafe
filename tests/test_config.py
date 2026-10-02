from walksafe.config import CFG, load


def test_key_values():
    assert CFG.models.yolo_conf == 0.35
    assert CFG.models.depth_max_age_s == 0.4
    assert CFG.models.resize_width == 518
    assert CFG.models.agent_classes == (0, 1, 2, 3, 5, 7)
    assert CFG.agents.ttc_critical_s < CFG.agents.ttc_high_s < CFG.agents.ttc_moderate_s


def test_profile_geometry():
    assert CFG.profile.needed_width_m == 0.75
    assert round(CFG.profile.focal_px(518), 1) == 625.3      # 45 degrees


def test_yaml_override_changes_only_the_named_value(tmp_path):
    path = tmp_path / "exp.yaml"
    path.write_text("agents:\n  ttc_critical_s: 1.5\n")
    cfg = load(str(path))
    assert cfg.agents.ttc_critical_s == 1.5
    assert cfg.agents.ttc_high_s == CFG.agents.ttc_high_s
    assert cfg.models == CFG.models


def test_no_override_without_a_path(monkeypatch):
    monkeypatch.delenv("WALKSAFE_CONFIG", raising=False)
    assert load() == CFG


def test_depth_model_can_be_picked_by_name(monkeypatch):
    monkeypatch.delenv("WALKSAFE_CONFIG", raising=False)
    monkeypatch.setenv("WALKSAFE_DEPTH_MODEL", "depthpro")
    assert load().models.depth_model_id == "apple/DepthPro-hf"
    monkeypatch.setenv("WALKSAFE_DEPTH_MODEL", "indoor")
    assert "Indoor" in load().models.depth_model_id
