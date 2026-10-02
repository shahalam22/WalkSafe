import logging

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, DepthProForDepthEstimation

log = logging.getLogger(__name__)


class DepthPro:
    def __init__(self, model_id: str, device: str, fp16: bool = False):
        log.info("Loading DepthPro (%s, fp16=%s)", model_id, fp16)
        self.device    = device
        self.dtype     = torch.float16 if fp16 else torch.float32
        # AutoImageProcessor: transformers 5 dropped DepthProImageProcessorFast.
        self.processor = AutoImageProcessor.from_pretrained(model_id, use_fast=True)
        self.model     = DepthProForDepthEstimation.from_pretrained(model_id).to(device, self.dtype).eval()
        self.last_fov_deg: float | None = None

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        H, W   = frame_bgr.shape[:2]
        pil    = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        inputs = self.processor(images=[pil], return_tensors="pt")
        inputs = {k: v.to(self.device, self.dtype) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model(**inputs)
        post = self.processor.post_process_depth_estimation(outputs, target_sizes=[(H, W)])[0]
        fov  = post.get("field_of_view")
        self.last_fov_deg = None if fov is None else float(fov)
        return post["predicted_depth"].float().cpu().numpy()
