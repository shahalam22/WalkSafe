"""Every tunable value in one place (NFR-16).

Set WALKSAFE_CONFIG to a YAML file to override values for an experiment:

    agents:
      ttc_emergency: 1.5
"""
import os
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class ModelConfig:
    depth_model_id:       str   = "apple/DepthPro-hf"
    yolo_model:           str   = "yolov8n.pt"
    yolo_conf:            float = 0.35
    depth_every_n_frames: int   = 5


@dataclass(frozen=True)
class CameraConfig:
    resize_width: int   = 518
    fov_deg:      float = 70.0


@dataclass(frozen=True)
class EgoConfig:
    background_frac: float = 0.10
    lateral_thresh:  float = 0.65
    rotation_thresh: float = 0.65
    mag_still:       float = 0.30
    mag_very_slow:   float = 0.80
    mag_slow:        float = 2.00
    mag_normal:      float = 4.50


@dataclass(frozen=True)
class AgentConfig:
    motion_window:    int   = 8
    ttc_emergency:    float = 1.0
    ttc_critical:     float = 2.0
    ttc_urgent:       float = 4.0
    close_distance_m: float = 3.0


@dataclass(frozen=True)
class OpeningConfig:
    min_width_px:     int   = 50
    surface_top_frac: float = 0.62
    comfortable_m:    float = 1.2
    tight_m:          float = 0.6
    squeeze_m:        float = 0.3


@dataclass(frozen=True)
class QualityConfig:
    depth_sigma_reliable: float = 0.10
    depth_sigma_moderate: float = 0.25


@dataclass(frozen=True)
class UiConfig:
    depth_pct_low:      float = 2
    depth_pct_high:     float = 95
    flow_arrow_step:    int   = 30
    overhead_top_frac:  float = 0.18
    overhead_bot_frac:  float = 0.38
    advisory_height_px: int   = 130


@dataclass(frozen=True)
class Config:
    models:   ModelConfig   = field(default_factory=ModelConfig)
    camera:   CameraConfig  = field(default_factory=CameraConfig)
    ego:      EgoConfig     = field(default_factory=EgoConfig)
    agents:   AgentConfig   = field(default_factory=AgentConfig)
    openings: OpeningConfig = field(default_factory=OpeningConfig)
    quality:  QualityConfig = field(default_factory=QualityConfig)
    ui:       UiConfig      = field(default_factory=UiConfig)


def load(path: str | None = None) -> Config:
    cfg  = Config()
    path = path or os.environ.get("WALKSAFE_CONFIG")
    if not path:
        return cfg
    import yaml
    with open(path) as f:
        overrides = yaml.safe_load(f) or {}
    for section, values in overrides.items():
        cfg = replace(cfg, **{section: replace(getattr(cfg, section), **values)})
    return cfg


CFG = load()
