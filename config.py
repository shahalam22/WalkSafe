CFG = {
    # ── Models ──
    "depth_model_id":         "apple/DepthPro-hf",
    "yolo_model":             "yolov8n.pt",
    "yolo_conf":              0.35,

    # ── Depth ──
    "depth_every_n_frames":   5,      # used when depth_in_background is off
    "depth_in_background":    True,   # run depth in its own thread; frames use the newest depth map
    "depth_pct_low":          2,
    "depth_pct_high":         95,

    # ── Video ──
    "resize_width":           518,

    # ── Optical flow ──
    "flow_arrow_step":        30,

    # ── Gap detection ──
    "gap_min_width_px":       50,

    # ── Ego signal thresholds ──
    "fov_deg":                70.0,
    "ego_background_frac":    0.10,
    "flow_lateral_thresh":    0.65,
    "flow_rotation_thresh":   0.65,
    "flow_mag_still":         0.30,
    "flow_mag_very_slow":     0.80,
    "flow_mag_slow":          2.00,
    "flow_mag_normal":        4.50,

    # ── Agent tracking ──
    "motion_window":          8,

    # ── Risk / TTC ──
    "ttc_emergency":          1.0,
    "ttc_critical":           2.0,
    "ttc_urgent":             4.0,
    "depth_sigma_reliable":   0.10,
    "depth_sigma_moderate":   0.25,
    "gap_comfortable":        1.2,
    "gap_tight":              0.6,
    "gap_squeeze":            0.3,
    "close_distance_m":       3.0,

    # ── Zones ──
    "zone_overhead_top_frac": 0.18,
    "zone_overhead_bot_frac": 0.38,
    "zone_surface_top_frac":  0.62,

    # ── Advisory strip ──
    "advisory_height_px":     130,
}

# ── Server ────────────────────────────────────────────────────────────────────
# Secrets are never written here: SUPABASE_SECRET_KEY comes from the environment
# (Colab Secrets on Colab, the .env file locally).
SERVER = {
    "supabase_url":     "https://eihhhppmjaduxcqodfea.supabase.co",
    "port":             8000,
    "tunnel":           "cloudflared",   # "cloudflared", "gradio" or "none"
    "max_image_bytes":  2_000_000,
    "session_idle_s":   60,              # a session with no frames for this long is closed
    "view_jpeg_quality": 70,
}
