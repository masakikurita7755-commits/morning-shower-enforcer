import cv2
import numpy as np
import os
import json
from PIL import Image

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

class ShowerDetector:
    def __init__(self, calibration_path="calibration.json"):
        self.calibration_path = calibration_path
        # Load OpenCV Haar Cascade for face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        self.calibration_data = self.load_calibration()

        # Initialize Gemini Client if key is configured
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.use_gemini = bool(self.api_key and GEMINI_AVAILABLE and "YOUR_GEMINI" not in self.api_key)
        if self.use_gemini:
            try:
                self.client = genai.Client(api_key=self.api_key)
                print("Gemini AI Client initialized successfully.")
            except Exception as e:
                print(f"Error initializing Gemini client: {e}")
                self.use_gemini = False

    def load_calibration(self):
        """Loads calibration data from a JSON file if it exists."""
        if os.path.exists(self.calibration_path):
            try:
                with open(self.calibration_path, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                print(f"Error loading calibration data: {e}")
        return None

    def save_calibration(self, data):
        """Saves calibration data to a JSON file."""
        self.calibration_data = data
        try:
            with open(self.calibration_path, 'w') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving calibration data: {e}")
            return False

    def clear_calibration(self):
        """Removes current calibration."""
        self.calibration_data = None
        if os.path.exists(self.calibration_path):
            try:
                os.remove(self.calibration_path)
            except Exception as e:
                print(f"Error deleting calibration file: {e}")

    def pil_to_cv2(self, pil_image):
        """Converts a PIL Image (from Streamlit) to an OpenCV BGR image."""
        if isinstance(pil_image, Image.Image):
            # Convert PIL to RGB numpy array, then to BGR for OpenCV
            return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        return pil_image

    def detect_hair_roi(self, cv_image):
        """
        Detects the face and estimates the Hair Region of Interest (ROI).
        Returns:
            (hair_roi, face_box, hair_box)
            - hair_roi: cropped BGR image of the hair region (or None if face not found)
            - face_box: (x, y, w, h) of detected face
            - hair_box: (hx, hy, hw, hh) of estimated hair region
        """
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        # Detect faces
        faces = self.face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.1, 
            minNeighbors=5, 
            minSize=(100, 100)
        )

        if len(faces) == 0:
            return None, None, None

        # Pick the largest face detected
        face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = face

        # Estimate hair region relative to the face box
        # Hair width: slightly wider than the face
        hx_start = max(0, int(x - 0.1 * w))
        hx_end = min(cv_image.shape[1], int(x + 1.1 * w))
        
        # Hair height: above the forehead
        hy_start = max(0, int(y - 0.6 * h))
        hy_end = min(cv_image.shape[0], int(y + 0.1 * h)) # include top of face/forehead

        hw = hx_end - hx_start
        hh = hy_end - hy_start

        if hw <= 0 or hh <= 0:
            return None, (x, y, w, h), None

        hair_roi = cv_image[hy_start:hy_end, hx_start:hx_end]
        return hair_roi, (x, y, w, h), (hx_start, hy_start, hw, hh)

    def extract_features(self, hair_roi):
        """
        Extracts key metrics from the hair ROI:
        - Mean brightness (Grayscale)
        - Texture variance (Laplacian) to measure high frequency details (hair strands)
        """
        gray_hair = cv2.cvtColor(hair_roi, cv2.COLOR_BGR2GRAY)
        
        # 1. Mean brightness
        mean_brightness = float(np.mean(gray_hair))
        
        # 2. Laplacian Variance (Texture detail score)
        # Dry hair has high variance due to distinct dry hair strands/edges.
        # Wet hair clumps together and has smoother highlights, lowering the variance.
        laplacian = cv2.Laplacian(gray_hair, cv2.CV_64F)
        texture_var = float(np.var(laplacian))

        return {
            "mean_brightness": mean_brightness,
            "texture_variance": texture_var
        }

    def calibrate_baseline(self, pil_image):
        """
        Analyzes a baseline (dry hair) image and saves it.
        Returns: (success, message)
        """
        cv_image = self.pil_to_cv2(pil_image)
        hair_roi, face_box, hair_box = self.detect_hair_roi(cv_image)

        if hair_roi is None:
            return False, "얼굴을 감지할 수 없습니다. (No face detected. Please position your face clearly in front of the camera.)"

        features = self.extract_features(hair_roi)
        
        success = self.save_calibration(features)
        if success:
            return True, f"Calibration complete! Saved dry baseline: Brightness={features['mean_brightness']:.1f}, Texture Variance={features['texture_variance']:.1f}"
        else:
            return False, "Failed to save calibration data."

    def is_wet_hair(self, pil_image):
        """
        Determines if the hair in the image is wet.
        If Gemini API key is configured, uses Gemini AI to analyze the image.
        Otherwise, falls back to the OpenCV dry-baseline comparison method.
        Returns:
            (is_wet, message, details_dict)
        """
        if self.use_gemini:
            prompt = (
                "Analyze the person's hair in this image. Is the hair wet (meaning they just took a shower) or dry?\n"
                "Provide a JSON response containing two keys:\n"
                "1. 'is_wet': a boolean (true if hair is wet/damp, false if it is dry)\n"
                "2. 'explanation': a short, concise description (max 2 sentences) in Japanese explaining what you see that leads to this conclusion (e.g. hair looks shiny and clumped, or hair looks fluffy and dry)."
            )
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[pil_image, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                result_json = json.loads(response.text)
                is_wet = result_json.get("is_wet", False)
                explanation = result_json.get("explanation", "")
                
                details = {
                    "mode": "gemini",
                    "explanation": explanation,
                    "is_wet": is_wet
                }
                
                if is_wet:
                    msg = f"Verification SUCCESS (Gemini AI): {explanation}"
                else:
                    msg = f"Verification FAILED (Gemini AI): {explanation}"
                    
                return is_wet, msg, details
            except Exception as e:
                print(f"Gemini API analysis failed, falling back to local OpenCV: {e}")

        # Fallback to local OpenCV-based analysis
        if not self.calibration_data:
            return False, "Calibration required first! (Or configure GEMINI_API_KEY in .env)", {}

        cv_image = self.pil_to_cv2(pil_image)
        hair_roi, face_box, hair_box = self.detect_hair_roi(cv_image)

        if hair_roi is None:
            return False, "No face detected in the image. Please try again.", {}

        current_features = self.extract_features(hair_roi)
        
        baseline_brightness = self.calibration_data["mean_brightness"]
        baseline_variance = self.calibration_data["texture_variance"]
        
        current_brightness = current_features["mean_brightness"]
        current_variance = current_features["texture_variance"]

        # Calculate ratios
        brightness_ratio = current_brightness / baseline_brightness if baseline_brightness > 0 else 1.0
        variance_ratio = current_variance / baseline_variance if baseline_variance > 0 else 1.0

        # Heuristics:
        # 1. Wet hair is darker: brightness drops by more than 12% (ratio < 0.88)
        # 2. Wet hair clumps: texture details drop by more than 25% (ratio < 0.75)
        # We'll use a combined heuristic: either a significant drop in both, or an extreme drop in one.
        is_darker = brightness_ratio < 0.88
        is_smoother = variance_ratio < 0.75

        # Determine wetness
        is_wet = is_darker or is_smoother

        details = {
            "baseline_brightness": round(baseline_brightness, 2),
            "current_brightness": round(current_brightness, 2),
            "brightness_ratio": round(brightness_ratio, 3),
            "baseline_variance": round(baseline_variance, 2),
            "current_variance": round(current_variance, 2),
            "variance_ratio": round(variance_ratio, 3),
            "is_darker_than_threshold": is_darker,
            "is_smoother_than_threshold": is_smoother
        }

        if is_wet:
            msg = "Verification SUCCESS: Wet hair detected! Shower confirmed."
        else:
            msg = "Verification FAILED: Hair appears dry. Did you actually shower?"

        return is_wet, msg, details

    def get_overlay_image(self, pil_image):
        """
        Helper method to draw bounding boxes on the image for visual feedback.
        Returns a PIL Image with rectangles drawn.
        """
        cv_image = self.pil_to_cv2(pil_image)
        _, face_box, hair_box = self.detect_hair_roi(cv_image)

        if face_box is not None:
            # Draw Face box (Green)
            x, y, w, h = face_box
            cv2.rectangle(cv_image, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(cv_image, "Face", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if hair_box is not None:
            # Draw Hair ROI box (Blue)
            hx, hy, hw, hh = hair_box
            cv2.rectangle(cv_image, (hx, hy), (hx + hw, hy + hh), (255, 0, 0), 2)
            cv2.putText(cv_image, "Hair ROI", (hx, hy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        # Convert back to PIL for Streamlit
        cv_rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(cv_rgb)
