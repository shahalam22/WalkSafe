import torch
from ultralytics import YOLO
from transformers import DepthProImageProcessorFast, DepthProForDepthEstimation
from torchvision.models.optical_flow import raft_small, Raft_Small_Weights
from config import CFG
import audio.speaker as speaker
import storage

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ── Module-level singletons — loaded once, reused everywhere ──────────────────
depth_processor  = None
depth_model      = None
raft_model       = None
_raft_transforms = None
yolo_model       = None


def load_all():
    global depth_processor, depth_model, raft_model, _raft_transforms, yolo_model

    print(f"Device: {DEVICE}\n")

    # ── Depth Pro ─────────────────────────────────────────────────────────────
    print(f"Loading DepthPro ({CFG['depth_model_id']})...")
    depth_processor = DepthProImageProcessorFast.from_pretrained(CFG["depth_model_id"])
    depth_model     = DepthProForDepthEstimation.from_pretrained(CFG["depth_model_id"])
    depth_model     = depth_model.to(DEVICE).eval()
    print("✅ DepthPro ready\n")

    # ── RAFT-Small ────────────────────────────────────────────────────────────
    print("Loading RAFT-Small...")
    _weights         = Raft_Small_Weights.DEFAULT
    _raft_transforms = _weights.transforms()
    raft_model       = raft_small(weights=_weights).to(DEVICE).eval()
    print("✅ RAFT-Small ready\n")

    # ── YOLOv8 ───────────────────────────────────────────────────────────────
    print(f"Loading YOLO ({CFG['yolo_model']})...")
    yolo_model = YOLO(CFG["yolo_model"])
    print("✅ YOLO ready\n")

    # ── Speaker — last, non-critical ──────────────────────────────────────────
    # Initialised after vision models so a TTS failure never blocks the pipeline
    speaker.init()
    storage.init()

    print("✅ All models loaded")


def is_ready():
    """Quick health check — call from ui.py before accepting frames."""
    return all([
        depth_processor  is not None,
        depth_model      is not None,
        raft_model       is not None,
        _raft_transforms is not None,
        yolo_model       is not None,
    ])