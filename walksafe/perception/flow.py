import logging

import cv2
import numpy as np
import torch
from torchvision.models.optical_flow import Raft_Small_Weights, raft_small

log = logging.getLogger(__name__)


class RaftSmall:
    def __init__(self, device: str, scale: float = 1.0):
        log.info("Loading RAFT-Small (input scale %.2f)", scale)
        weights         = Raft_Small_Weights.DEFAULT
        self.device     = device
        self.scale      = scale
        self.transforms = weights.transforms()
        self.model      = raft_small(weights=weights).to(device).eval()

    def compute(self, prev_bgr: np.ndarray, curr_bgr: np.ndarray) -> np.ndarray:
        if self.scale != 1.0:
            H, W  = prev_bgr.shape[:2]
            small = (int(W * self.scale), int(H * self.scale))
            flow  = self._raft(cv2.resize(prev_bgr, small), cv2.resize(curr_bgr, small))
            return cv2.resize(flow, (W, H)) / self.scale
        return self._raft(prev_bgr, curr_bgr)

    def _raft(self, prev_bgr, curr_bgr):
        H, W = prev_bgr.shape[:2]
        ph   = (8 - H % 8) % 8
        pw   = (8 - W % 8) % 8

        def to_t(bgr):
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            t   = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).to(self.device)
            if ph > 0 or pw > 0:
                t = torch.nn.functional.pad(
                    t.float(), (0, pw, 0, ph), mode="replicate").to(torch.uint8)
            return t

        t1, t2   = to_t(prev_bgr), to_t(curr_bgr)
        t1n, t2n = self.transforms(t1, t2)
        with torch.no_grad():
            flow_list = self.model(t1n.to(self.device), t2n.to(self.device))
        flow = flow_list[-1][0][:, :H, :W]                    # [2,H,W]
        return flow.permute(1, 2, 0).cpu().numpy()           # [H,W,2]
