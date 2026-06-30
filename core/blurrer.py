"""
Blurring Module
===============
Applies different types of privacy filters (Gaussian, Pixelate, Black Box)
to regions of an image. Includes standard padding around bounding boxes
to ensure complete coverage of identities.
"""

import cv2
import numpy as np
from typing import Tuple

from config import BLUR_BBOX_PADDING

class FaceBlurrer:
    def __init__(self, blur_type: str = "gaussian", intensity: int = 50):
        """
        blur_type: 'gaussian', 'pixelate', 'black_box'
        intensity: 1 to 100
        """
        self.blur_type = blur_type.lower()
        self.intensity = max(1, min(100, intensity))
        
    def _pad_bbox(self, bbox: Tuple[int, int, int, int], max_w: int, max_h: int) -> Tuple[int, int, int, int]:
        """Apply padding to the bounding box."""
        x, y, w, h = bbox
        
        pad_w = int(w * BLUR_BBOX_PADDING)
        pad_h = int(h * BLUR_BBOX_PADDING)
        
        new_x = max(0, x - pad_w)
        new_y = max(0, y - pad_h)
        new_w = min(max_w - new_x, w + 2 * pad_w)
        new_h = min(max_h - new_y, h + 2 * pad_h)
        
        return (new_x, new_y, new_w, new_h)

    def _apply_gaussian(self, face_region: np.ndarray) -> np.ndarray:
        """Apply Gaussian blur."""
        # Significantly increase kernel size for heavier blur
        k = int((self.intensity / 100.0) * 150) + 15
        if k % 2 == 0:
            k += 1
            
        blurred = cv2.GaussianBlur(face_region, (k, k), 0)
        
        # Multiple passes for higher intensity
        if self.intensity >= 40:
            blurred = cv2.GaussianBlur(blurred, (k, k), 0)
        if self.intensity >= 80:
            blurred = cv2.GaussianBlur(blurred, (k, k), 0)
            
        return blurred

    def _apply_pixelate(self, face_region: np.ndarray) -> np.ndarray:
        """Apply Pixelation effect."""
        h, w = face_region.shape[:2]
        
        # Increase downsample factor for larger blocks (heavier pixelation)
        factor = int((self.intensity / 100.0) * 35) + 5
        
        small_w = max(1, w // factor)
        small_h = max(1, h // factor)
        
        # Downsample
        temp = cv2.resize(face_region, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
        # Upsample
        pixelated = cv2.resize(temp, (w, h), interpolation=cv2.INTER_NEAREST)
        
        return pixelated

    def _apply_black_box(self, face_region: np.ndarray) -> np.ndarray:
        """Apply solid black box with feathered edges based on intensity."""
        h, w = face_region.shape[:2]
        
        # Create a black image
        black = np.zeros_like(face_region)
        
        # Lower feather amount so the black box is more prominent and opaque
        feather_amount = int((100 - self.intensity) / 100.0 * min(w, h) * 0.15)
        
        if feather_amount > 0:
            # Create mask for feathering
            mask = np.zeros((h, w), dtype=np.float32)
            cv2.rectangle(mask, (feather_amount, feather_amount), 
                          (w - feather_amount, h - feather_amount), 1.0, -1)
            
            k = feather_amount * 2 + 1
            mask = cv2.GaussianBlur(mask, (k, k), 0)
            
            mask_3c = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            
            # Blend
            return (face_region * (1 - mask_3c) + black * mask_3c).astype(np.uint8)
        else:
            return black

    def apply(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Apply the selected blur type to the bounding box region in the frame."""
        h_frame, w_frame = frame.shape[:2]
        
        # Pad bbox
        px, py, pw, ph = self._pad_bbox(bbox, w_frame, h_frame)
        
        if pw <= 0 or ph <= 0:
            return frame
            
        # Extract region
        face_region = frame[py:py+ph, px:px+pw]
        
        # Apply effect
        if self.blur_type == "gaussian":
            processed_region = self._apply_gaussian(face_region)
        elif self.blur_type == "pixelate":
            processed_region = self._apply_pixelate(face_region)
        elif self.blur_type == "black box":
            processed_region = self._apply_black_box(face_region)
        else:
            processed_region = self._apply_gaussian(face_region) # default fallback
            
        # Place back into frame
        result = frame.copy()
        result[py:py+ph, px:px+pw] = processed_region
        
        return result
