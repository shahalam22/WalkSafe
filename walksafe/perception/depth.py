import logging

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import DepthProForDepthEstimation, DepthProImageProcessorFast

log = logging.getLogger(__name__)


class DepthPro:
    def __init__(self, model_id: str, device: str):
        log.info("Loading DepthPro (%s)", model_id)
        self.device    = device
        self.processor = DepthProImageProcessorFast.from_pretrained(model_id)
        self.model     = DepthProForDepthEstimation.from_pretrained(model_id).to(device).eval()

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        H, W   = frame_bgr.shape[:2]
        pil    = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        inputs = self.processor(images=[pil], return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self.model(**inputs)
        post = self.processor.post_process_depth_estimation(outputs, target_sizes=[(H, W)])
        return post[0]["predicted_depth"].cpu().numpy().astype(np.float32)
