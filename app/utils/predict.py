import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.metrics import Precision, Recall
import numpy as np

from app.utils.preprocess import preprocess_medical_image

class F1Score(tf.keras.metrics.Metric):
    def __init__(self, name='f1_score', threshold=0.5, **kwargs):
        super(F1Score, self).__init__(name=name, **kwargs)
        self.precision = Precision(thresholds=threshold)
        self.recall = Recall(thresholds=threshold)

    def update_state(self, y_true, y_pred, sample_weight=None):
        self.precision.update_state(y_true, y_pred, sample_weight)
        self.recall.update_state(y_true, y_pred, sample_weight)

    def result(self):
        p = self.precision.result()
        r = self.recall.result()
        return 2 * ((p * r) / (p + r + tf.keras.backend.epsilon()))

    def reset_state(self):
        self.precision.reset_state()
        self.recall.reset_state()

def focal_loss(gamma=3.0, alpha=0.6):
    def focal_loss_fn(y_true, y_pred):
        y_true = tf.cast(y_true, tf.float32)
        y_pred = tf.cast(y_pred, tf.float32)
        epsilon = tf.keras.backend.epsilon()
        y_pred = tf.clip_by_value(y_pred, epsilon, 1.0 - epsilon)
        cross_entropy = -y_true * tf.math.log(y_pred) - (1 - y_true) * tf.math.log(1 - y_pred)
        p_t = y_true * y_pred + (1 - y_true) * (1 - y_pred)
        modulating_factor = tf.pow(1.0 - p_t, gamma)
        alpha_factor = y_true * alpha + (1 - y_true) * (1 - alpha)
        loss = alpha_factor * modulating_factor * cross_entropy
        return tf.reduce_mean(loss)
    return focal_loss_fn

# Configura los objetos personalizados
custom_objects = {
    'F1Score': F1Score,
    'focal_loss_fn': focal_loss(gamma=3.0, alpha=0.6)
}

def load_stroke_model(model_path):
    try:
        tf.keras.backend.clear_session()
        model = load_model(model_path, custom_objects=custom_objects, compile=True)
        model.load_weights(model_path)
        return model
    except Exception as e:
        raise ValueError(f"Error loading model: {str(e)}")

# Umbral óptimo determinado por tu Fold 5
OPTIMAL_THRESHOLD = 0.4469

MODEL_PATH = "models/best_fold_5_el_mejor_de_los_5_folds.h5"

try:
    model = load_stroke_model(MODEL_PATH)
    print(f"Model loaded successfully! Using optimal threshold: {OPTIMAL_THRESHOLD}")
except Exception as e:
    print(f"Failed to load model: {e}")
    model = None

async def predict_stroke(image_content: bytes):
    if model is None:
        raise Exception("Model not loaded")

    try:
        processed_image = preprocess_medical_image(image_content)
        processed_image = np.expand_dims(processed_image, axis=0)

        # Obtener probabilidad cruda del modelo
        prediction = model.predict(processed_image)
        probability = float(prediction[0][0])

        # Aplicar umbral óptimo (44.69%)
        diagnosis = "Stroke" if probability >= OPTIMAL_THRESHOLD else "Normal"

        # Calcular confianza relativa al umbral
        if diagnosis == "Stroke":
            confidence = (probability - OPTIMAL_THRESHOLD) / (1 - OPTIMAL_THRESHOLD)
        else:
            confidence = (OPTIMAL_THRESHOLD - probability) / OPTIMAL_THRESHOLD

        # Asegurar que la confianza esté en [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "probability": probability,
            "threshold_used": OPTIMAL_THRESHOLD
        }
    except Exception as e:
        raise Exception(f"Prediction error: {str(e)}")