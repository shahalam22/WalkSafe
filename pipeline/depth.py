import torch
import numpy as np
import cv2
from PIL import Image
import models
from config import CFG


def estimate(frame_bgr, H, W):
    pil    = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
    inputs = models.depth_processor(images=[pil], return_tensors="pt")
    inputs = {k: v.to(models.DEVICE) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = models.depth_model(**inputs)
    post = models.depth_processor.post_process_depth_estimation(
        outputs, target_sizes=[(H, W)])
    return post[0]["predicted_depth"].cpu().numpy().astype(np.float32)


def colormap(depth_arr):
    lo  = np.percentile(depth_arr, CFG["depth_pct_low"])
    hi  = np.percentile(depth_arr, CFG["depth_pct_high"])
    clp = np.clip(depth_arr, lo, hi)
    n   = ((clp - lo) / (hi - lo + 1e-8) * 255).astype(np.uint8)
    return cv2.applyColorMap(n, cv2.COLORMAP_VIRIDIS)