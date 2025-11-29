# =============================================================
#  API CARDIOVASCULAR - MODELO + RECOMENDACIONES CON IA
# =============================================================

import os
import time
import json
import threading
import numpy as np
import joblib
import requests
from typing import Dict, Any, List
from functools import lru_cache
from dotenv import load_dotenv

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI



# -------------------------------------------------------------
# Cargar variables de entorno (.env)
# -------------------------------------------------------------
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

print("Usando .env en:", ENV_PATH)
print("DEBUG OPENAI_API_KEY:", repr(os.environ.get("OPENAI_API_KEY")))


print("DEBUG OPENAI_API_KEY:", repr(os.environ.get("OPENAI_API_KEY")))
print("DEBUG MODEL_PATH:", repr(os.environ.get("MODEL_PATH")))


# -------------------------------------------------------------
# Configuración general
# -------------------------------------------------------------
MODEL_PATH = os.environ.get("MODEL_PATH", "modelo_cardiovascular.pkl")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "8"))
OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "2"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
client = OpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------------------
# Inicialización de Flask
# -------------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# -------------------------------------------------------------
# Cargar modelo
# -------------------------------------------------------------
try:
    modelo = joblib.load(MODEL_PATH)
    print(f"✅ Modelo cargado correctamente desde: {MODEL_PATH}")
except Exception as e:
    print(f"❌ ERROR al cargar el modelo: {e}")
    modelo = None

# -------------------------------------------------------------
# Decorador para cache con tiempo de vida (TTL)
# -------------------------------------------------------------
def ttl_cache(ttl_seconds):
    def wrapper(fn):
        cache = {}
        lock = threading.Lock()
        def make_key(args, kwargs):
            try:
                return json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
            except Exception:
                return str((args, kwargs))
        def wrapped(*args, **kwargs):
            key = make_key(args, kwargs)
            now = time.time()
            with lock:
                if key in cache:
                    value, ts = cache[key]
                    if now - ts < ttl_seconds:
                        return value
                res = fn(*args, **kwargs)
                cache[key] = (res, now)
            return res
        return wrapped
    return wrapper

def _to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default

# -------------------------------------------------------------
# Recomendaciones locales (reglas) como fallback
# -------------------------------------------------------------
def rule_based_recommendations(data: Dict[str, Any], pred: int, prob: float) -> List[str]:
    # Normalizar tipos (vienen como strings desde el front)
    cholesterol = _to_float(data.get("cholesterol", 0))
    bp = _to_float(data.get("bp", 0))
    smoke = _to_int(data.get("smoke", 0))
    alcohol = _to_int(data.get("alcohol", 0))
    physical_activity = _to_float(data.get("physical_activity", 0))
    stress_level = _to_float(data.get("stress_level", 0))
    family_history = _to_int(data.get("family_history", 0))

    recs = []
    if pred == 1:
        recs.append("⚠️ Riesgo cardiovascular detectado. Consulte un médico pronto.")
    else:
        recs.append("✅ Riesgo bajo detectado. Mantenga hábitos saludables.")

    if cholesterol > 240:
        recs.append("Nivel de colesterol alto: reduzca grasas saturadas y aumente frutas y fibra.")
    if bp > 140:
        recs.append("Presión arterial elevada: controle el estrés y limite el consumo de sal.")
    if smoke == 1:
        recs.append("Fumar aumenta el riesgo cardíaco. Busque ayuda para dejarlo.")
    if alcohol == 1:
        recs.append("Modere el consumo de alcohol; afecta presión y corazón.")
    if physical_activity < 3:
        recs.append("Aumente su actividad física a al menos 150 minutos semanales.")
    if stress_level > 3:
        recs.append("Niveles altos de estrés: practique relajación o meditación.")
    if family_history == 1:
        recs.append("Antecedentes familiares: realice chequeos preventivos con más frecuencia.")

    recs.append("Monitoree peso, colesterol y presión periódicamente.")
    return recs


# -------------------------------------------------------------
# Construcción del prompt para la IA
# -------------------------------------------------------------
def build_prompt(data: Dict[str, Any], pred: int, prob: float) -> str:
    prompt = f"""
Eres un asistente médico profesional y empático. Analiza el perfil de riesgo cardiovascular
y genera recomendaciones personalizadas en español, breves y prácticas.

Datos del paciente:
- Edad: {data.get("age")}
- Género: {"masculino" if int(data.get("gender", 0)) == 1 else "femenino"}
- Colesterol: {data.get("cholesterol")} mg/dL
- Presión arterial: {data.get("bp")} mmHg
- Glucosa: {data.get("glucose")}
- IMC: {data.get("BMI")}
- Actividad física: {data.get("physical_activity")} h/semana
- Fuma: {"sí" if int(data.get("smoke", 0)) == 1 else "no"}
- Alcohol: {"sí" if int(data.get("alcohol", 0)) == 1 else "no"}
- Estrés: {data.get("stress_level")}
- Antecedentes familiares: {data.get("family_history")}
- Riesgo predicho: {"ALTO" if pred==1 else "BAJO"} ({prob*100:.1f}%)

Genera:
1️⃣ Un resumen del estado (1-2 líneas).
2️⃣ Tres recomendaciones a corto, mediano y largo plazo.
3️⃣ Una advertencia si hay riesgo alto.
4️⃣ Una nota de precaución aclarando que esto no sustituye consulta médica.

Responde SOLO en formato JSON:
{{
  "summary": "...",
  "recommendations": ["...", "...", "..."],
  "warning": "...",
  "disclaimer": "..."
}}
"""
    return prompt

# -------------------------------------------------------------
# Llamada a OpenAI con reintentos
# -------------------------------------------------------------
def call_openai(prompt: str) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("No se configuró OPENAI_API_KEY en el entorno.")

    # Usamos el cliente global creado arriba: client = OpenAI(api_key=OPENAI_API_KEY)

    for attempt in range(OPENAI_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Eres un asistente médico confiable y preciso."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.4,
                # si quieres, puedes controlar timeout a nivel cliente en vez de aquí
            )
            text = response.choices[0].message.content
            start, end = text.find("{"), text.rfind("}")
            return json.loads(text[start:end+1])
        except Exception as e:
            if attempt == OPENAI_MAX_RETRIES:
                raise RuntimeError(f"Falla al generar texto IA: {e}")
            time.sleep(1)


# -------------------------------------------------------------
# Endpoint principal de predicción
# -------------------------------------------------------------
@app.route("/predict", methods=["POST"])
def predict():
    if modelo is None:
        return jsonify({"error": "Modelo no cargado."}), 500

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON no proporcionado."}), 400

    try:
        # Los 13 parámetros esperados
        inputs = [
            float(data.get("age", 0)),
            int(data.get("gender", 0)),
            float(data.get("cholesterol", 0)),
            float(data.get("bp", 0)),
            int(data.get("smoke", 0)),
            int(data.get("alcohol", 0)),
            float(data.get("physical_activity", 0)),
            float(data.get("glucose", 0)),
            float(data.get("height", 0)),
            float(data.get("weight", 0)),
            float(data.get("BMI", 0)),
            int(data.get("family_history", 0)),
            float(data.get("stress_level", 0))
        ]
    except Exception as e:
        return jsonify({"error": f"Error en los datos: {e}"}), 400

    try:
        pred = int(modelo.predict([inputs])[0])
        prob = modelo.predict_proba([inputs])[0][1] if hasattr(modelo, "predict_proba") else pred
    except Exception as e:
        return jsonify({"error": f"Error durante la predicción: {e}"}), 500

    # IA o fallback
    try:
        llm_data = call_openai(build_prompt(data, pred, prob))
    except Exception as e:
        llm_data = None
        app.logger.warning(f"IA no disponible, fallback: {e}")

    final_recs = llm_data or {
        "summary": "Resultado generado localmente.",
        "recommendations": rule_based_recommendations(data, pred, prob)[:3],
        "warning": "",
        "disclaimer": "Esta información es automática y no sustituye la consulta médica."
    }

    return jsonify({
        "prediccion": pred,
        "probabilidad": round(float(prob) * 100, 2),
        "recomendaciones": final_recs
    })

# -------------------------------------------------------------
# Endpoint raíz
# -------------------------------------------------------------
@app.route("/")
def index():
    # servirá static/index.html
    return app.send_static_file("index.html")


# -------------------------------------------------------------
# Ejecutar servidor
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
