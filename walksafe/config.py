"""Every tunable value in one place (NFR-16).

Set WALKSAFE_CONFIG to a YAML file to override values for an experiment:

    agents:
      ttc_critical_s: 1.5

Values marked "untuned" are first guesses that still need checking against
recorded clips.
"""
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace


@dataclass(frozen=True)
class Profile:
    """One user's setup. These are the defaults until the phone sends its own (FR-23)."""
    camera_fov_deg:     float = 70.0
    shoulder_width_m:   float = 0.45
    clearance_margin_m: float = 0.30
    depth_scale:        float = 1.0

    @property
    def needed_width_m(self) -> float:
        return self.shoulder_width_m + self.clearance_margin_m

    def focal_px(self, image_width: int) -> float:
        return image_width / (2 * math.tan(math.radians(self.camera_fov_deg) / 2))


@dataclass(frozen=True)
class ModelConfig:
    depth_model_id:  str   = "apple/DepthPro-hf"
    yolo_model:      str   = "yolov8n.pt"
    yolo_conf:       float = 0.35
    # COCO ids for the agents FR-3 names: person, bicycle, car, motorcycle, bus, truck.
    agent_classes:   tuple[int, ...] = (0, 1, 2, 3, 5, 7)
    depth_max_age_s: float = 0.4          # SRS §7.3
    resize_width:    int   = 518
    # Speed options measured by scripts/benchmark.py (NFR-4).
    depth_fp16:      bool  = False
    flow_scale:      float = 1.0          # RAFT runs on frames scaled by this
    # ByteTrack, with a shorter lost-track buffer than the 30-frame default
    # because frames arrive at 1-2 fps, not 30.
    track_high_thresh: float = 0.25
    track_low_thresh:  float = 0.1
    new_track_thresh:  float = 0.25
    track_buffer:      int   = 10
    match_thresh:      float = 0.8


@dataclass(frozen=True)
class AgentConfig:
    motion_window_s:     float = 2.0      # speeds are fitted over this much track history
    min_track_points:    int   = 3
    min_track_span_s:    float = 0.3
    forget_after_s:      float = 3.0      # drop a track not seen for this long
    box_lower_frac:      float = 0.4      # distance comes from the lower part of the box
    dist_percentile:     float = 10
    foreground_depth_m:  float = 1.0      # depth spread is measured within this of the near surface
    approach_speed_ms:   float = 0.3      # untuned
    crossing_speed_ms:   float = 0.4      # untuned
    ttc_min_closing_ms:  float = 0.1
    ttc_max_s:           float = 99.0
    ttc_critical_s:      float = 1.0
    ttc_high_s:          float = 2.0
    ttc_moderate_s:      float = 4.0
    critical_distance_m: float = 1.0
    close_distance_m:    float = 3.0


@dataclass(frozen=True)
class EgoConfig:
    grid_step_px:       int   = 8
    min_depth_m:        float = 0.5
    max_depth_m:        float = 12.0
    min_points:         int   = 50
    still_speed_ms:     float = 0.15     # untuned
    slow_speed_ms:      float = 0.6
    fast_speed_ms:      float = 1.6
    step_speed_ms:      float = 0.3      # untuned
    turn_rate_dps:      float = 15.0     # untuned
    stopping_trend_ms:  float = -0.25
    speed_history_len:  int   = 3
    max_interval_s:     float = 2.0      # older frame pairs are too far apart for flow


@dataclass(frozen=True)
class OpeningConfig:
    # Rows that see things at body height when the phone is held level.
    band_top_frac:       float = 0.38
    band_bottom_frac:    float = 0.62
    free_percentile:     float = 10
    # Look-ahead: openings are judged over this distance. It must cover the
    # server delay (about 1.4 m at walking pace) plus room to react. Untuned.
    min_free_distance_m: float = 3.5
    max_range_m:         float = 8.0     # SRS §1.2
    min_width_px:        int   = 8
    tight_extra_m:       float = 0.2     # an opening this close to the needed width is "tight"


@dataclass(frozen=True)
class DecisionConfig:
    crossing_ttc_s:    float = 3.0
    step_max_offset_m: float = 1.0       # openings further to the side need a turn
    confidence_low:    float = 0.6


@dataclass(frozen=True)
class QualityConfig:
    dark_max:             float = 40      # mean grey level, untuned
    bright_min:           float = 215     # untuned
    blur_min:             float = 60      # variance of the Laplacian, untuned
    blur_width_px:        int   = 160     # measured on a downscaled copy
    depth_sigma_reliable: float = 0.10    # relative spread of an agent's depth patch
    depth_sigma_moderate: float = 0.25
    moderate_depth_score: float = 0.7
    poor_depth_score:     float = 0.3
    new_track_score:      float = 0.5


@dataclass(frozen=True)
class ServerConfig:
    port:            int   = 7860
    # The phone page is served from GitHub Pages (FR-22) as well as from the server itself.
    allowed_origins: tuple[str, ...] = ("https://shahalam22.github.io",)
    session_idle_s:  float = 300.0
    # Below Starlette's 1 MiB spool limit, so an upload is never written to a temporary file.
    max_image_bytes: int   = 1_000_000


@dataclass(frozen=True)
class PhoneConfig:
    """Values the phone page uses. It receives them as /js/config.js, generated from here."""
    capture_fps:          float = 12.0
    upload_width:         int   = 518
    jpeg_quality:         float = 0.6     # about 30 KB a frame, inside NFR-15 at 2 fps
    analysis_width:       int   = 96
    analysis_height:      int   = 72
    dark_max:             float = 40
    bright_min:           float = 215
    blur_min:             float = 30      # variance of the Laplacian at 96x72, untuned
    stale_after_ms:       int   = 2000    # NFR-2
    request_timeout_ms:   int   = 3000
    max_messages_per_min: int   = 15      # NFR-13
    step_min_interval_ms: int   = 2000    # SRS UC-4: steps no more often than every 2 s
    # Expansion check (FR-16): block matching on the 96x72 copy. All untuned.
    expansion_block_px:     int   = 3       # half-size of the matched block (7x7)
    expansion_search_px:    int   = 4
    expansion_grid_px:      int   = 6
    expansion_min_texture:  float = 60      # grey-level variance a block needs to be tracked
    expansion_min_points:   int   = 20
    expansion_region_left:  float = 0.2     # where divergence is measured: the centre,
    expansion_region_right: float = 0.8     # above the nearby ground
    expansion_region_top:    float = 0.15
    expansion_region_bottom: float = 0.7
    expansion_max_gap_ms:   int   = 300     # frames further apart are not compared
    ttc_stop_s:             float = 1.5
    ttc_clear_s:            float = 2.5
    stop_frames:            int   = 3
    clear_frames:           int   = 5
    # Capability levels (SRS §2.2, FR-18 to FR-20)
    server_silent_ms:       int   = 2000
    announce_repeat_ms:     int   = 60000
    fault_onset_ms:         int   = 1000    # a fault must last this long before the level drops
    fault_clear_ms:         int   = 3000    # and be gone this long before it recovers
    check_dead_ms:          int   = 1000    # the on-phone check has not run for this long
    battery_warn_levels:    tuple[float, ...] = (0.20, 0.10)
    battery_end_level:      float = 0.05
    event_flush_ms:         int   = 5000
    max_queued_events:      int   = 500


@dataclass(frozen=True)
class UiConfig:
    depth_pct_low:      float = 2
    depth_pct_high:     float = 95
    flow_arrow_step:    int   = 30
    advisory_height_px: int   = 170


@dataclass(frozen=True)
class Config:
    profile:  Profile        = field(default_factory=Profile)
    models:   ModelConfig    = field(default_factory=ModelConfig)
    agents:   AgentConfig    = field(default_factory=AgentConfig)
    ego:      EgoConfig      = field(default_factory=EgoConfig)
    openings: OpeningConfig  = field(default_factory=OpeningConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    quality:  QualityConfig  = field(default_factory=QualityConfig)
    server:   ServerConfig   = field(default_factory=ServerConfig)
    phone:    PhoneConfig    = field(default_factory=PhoneConfig)
    ui:       UiConfig       = field(default_factory=UiConfig)


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


def phone_js(cfg: "Config") -> str:
    """The phone section as an ES module, so the page shares this file's values."""
    return f"export const CONFIG = Object.freeze({json.dumps(asdict(cfg.phone), indent=2)});\n"


CFG = load()
