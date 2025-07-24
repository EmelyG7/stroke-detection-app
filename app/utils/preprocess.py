from PIL import Image
import numpy as np
import cv2
from io import BytesIO

def preprocess_medical_image(image_content: bytes, target_size=(128, 128), debug=False):
    try:
        # Open image using PIL
        image = Image.open(BytesIO(image_content)).convert("RGB")
        # Convert to numpy array
        img = np.array(image)
        # Apply preprocessing from training script
        if img.dtype != np.uint8:
            img = (img * 255).astype(np.uint8)
        # Convert to grayscale for CLAHE
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        # Apply CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        # Normalize
        normalized = cv2.normalize(enhanced, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
        # Convert back to RGB
        rgb = cv2.cvtColor(normalized, cv2.COLOR_GRAY2RGB)
        # Resize to target size
        rgb = cv2.resize(rgb, target_size)
        # Normalize to [0, 1]
        rgb = rgb.astype(np.float32) / 255.0
        if debug:
            print(f"Processed image shape: {rgb.shape}, min: {rgb.min():.4f}, max: {rgb.max():.4f}")
        return rgb
    except Exception as e:
        raise Exception(f"Image preprocessing error: {str(e)}")