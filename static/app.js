// URL de la API: usa ruta relativa para que funcione en Render y local
const API_URL = "/predict";

// Helpers de vistas
const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-btn");

function showView(id) {
  views.forEach((v) => v.classList.remove("active"));
  document.getElementById(id).classList.add("active");

  navButtons.forEach((btn) =>
    btn.classList.toggle("active", btn.dataset.view === id)
  );
}

// Navegación desde la barra
navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    showView(btn.dataset.view);
  });
});

// Botón de "Evaluar mi riesgo" en la home
const btnStart = document.getElementById("btn-start");
if (btnStart) {
  btnStart.addEventListener("click", () => showView("form-view"));
}

// =======================
//   Lógica del formulario
// =======================

const form = document.getElementById("risk-form");
const statusText = document.getElementById("form-status");
const stressRange = document.getElementById("stress-range");
const stressValue = document.getElementById("stress-value");

const smokeToggle = document.getElementById("smoke-toggle");
const alcoholToggle = document.getElementById("alcohol-toggle");
const familyHistoryCheckbox = document.getElementById("family-history-checkbox");

// inputs ocultos para enviar 0/1
const hiddenSmoke = form?.querySelector('input[name="smoke"]');
const hiddenAlcohol = form?.querySelector('input[name="alcohol"]');
const hiddenFamilyHistory = form?.querySelector('input[name="family_history"]');

// Mostrar valor del slider de estrés
if (stressRange && stressValue) {
  stressRange.addEventListener("input", () => {
    stressValue.textContent = stressRange.value;
  });
}

// Actualizar valores de smoke / alcohol / antecedentes
if (smokeToggle && hiddenSmoke) {
  const updateSmoke = () => {
    hiddenSmoke.value = smokeToggle.checked ? "1" : "0";
  };
  smokeToggle.addEventListener("change", updateSmoke);
  updateSmoke();
}

if (alcoholToggle && hiddenAlcohol) {
  const updateAlcohol = () => {
    hiddenAlcohol.value = alcoholToggle.checked ? "1" : "0";
  };
  alcoholToggle.addEventListener("change", updateAlcohol);
  updateAlcohol();
}

if (familyHistoryCheckbox && hiddenFamilyHistory) {
  const updateFamilyHistory = () => {
    hiddenFamilyHistory.value = familyHistoryCheckbox.checked ? "1" : "0";
  };
  familyHistoryCheckbox.addEventListener("change", updateFamilyHistory);
  updateFamilyHistory();
}

// Calcular IMC automáticamente
function setupBMIAutoCalc() {
  const heightInput = form.querySelector('input[name="height"]');
  const weightInput = form.querySelector('input[name="weight"]');
  const bmiInput = form.querySelector('input[name="BMI"]');

  if (!heightInput || !weightInput || !bmiInput) return;

  const recalcBMI = () => {
    const h = parseFloat(heightInput.value);
    const w = parseFloat(weightInput.value);
    if (h > 0 && w > 0) {
      const meters = h / 100;
      const bmi = w / (meters * meters);
      bmiInput.value = bmi.toFixed(1);
    }
  };

  heightInput.addEventListener("input", recalcBMI);
  weightInput.addEventListener("input", recalcBMI);
}

if (form) {
  setupBMIAutoCalc();
}

// =======================
//   Manejo de resultados
// =======================

const resultView = document.getElementById("result-view");
const resultContainer = document.getElementById("result-container");
const resultEmpty = document.getElementById("result-empty");

const riskLabelEl = document.getElementById("risk-label");
const riskPercentEl = document.getElementById("risk-percent");
const riskCircle = document.getElementById("risk-circle");
const riskCircleText = document.getElementById("risk-circle-text");
const summaryText = document.getElementById("summary-text");
const warningBox = document.getElementById("warning-box");
const disclaimerText = document.getElementById("disclaimer-text");
const recommendationsList = document.getElementById("recommendations-list");
const btnNewEval = document.getElementById("btn-new-eval");

// Renderizar resultado
function renderResult(data) {
  const { prediccion, probabilidad, recomendaciones } = data;

  const risk = Number(probabilidad) || 0;

  // Texto de riesgo
  riskPercentEl.textContent = `${risk.toFixed(1)}%`;
  riskCircleText.textContent = `${risk.toFixed(0)}%`;

  // Nivel según predicción y probabilidad
  let level = "low";
  if (prediccion === 1 && risk >= 60) level = "high";
  else if (risk >= 30) level = "medium";

  riskLabelEl.className = "risk-tag " + level;
  riskLabelEl.textContent =
    level === "high"
      ? "RIESGO ALTO"
      : level === "medium"
      ? "RIESGO MODERADO"
      : "RIESGO BAJO";

  // Actualizar círculo de riesgo
  riskCircle.style.setProperty("--risk", risk.toString());
  riskCircle.classList.remove("low", "medium", "high");
  riskCircle.classList.add(level);

  // IA summary / warning / disclaimer
  if (recomendaciones) {
    summaryText.textContent = recomendaciones.summary || "";

    if (recomendaciones.warning && recomendaciones.warning.trim() !== "") {
      warningBox.textContent = "⚠ " + recomendaciones.warning;
      warningBox.classList.remove("hidden");
    } else {
      warningBox.classList.add("hidden");
    }

    disclaimerText.textContent =
      recomendaciones.disclaimer ||
      "Esta herramienta no sustituye una valoración médica profesional.";

    // Recomendaciones en tarjetas
    recommendationsList.innerHTML = "";
    if (Array.isArray(recomendaciones.recommendations)) {
      recomendaciones.recommendations.forEach((text) => {
        const card = document.createElement("div");
        card.className = "rec-card";

        const icon = document.createElement("div");
        icon.className = "rec-icon";
        icon.textContent = "💡";

        const body = document.createElement("div");
        body.className = "rec-text";
        body.textContent = text;

        card.appendChild(icon);
        card.appendChild(body);
        recommendationsList.appendChild(card);
      });
    }
  }

  resultEmpty.style.display = "none";
  resultContainer.classList.remove("hidden");

  // Ir a la vista de resultado
  showView("result-view");
}

// =======================
//   Envío del formulario
// =======================

if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    statusText.textContent = "Generando diagnóstico...";
    const submitBtn = document.getElementById("btn-submit");
    submitBtn.disabled = true;

    const formData = new FormData(form);
    const payload = {};

    formData.forEach((value, key) => {
      payload[key] = value;
    });

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error("Error en la API");
      }

      const json = await res.json();
      renderResult(json);
      statusText.textContent = "";
    } catch (err) {
      console.error(err);
      statusText.textContent =
        "Ocurrió un error al generar el diagnóstico. Intenta nuevamente.";
    } finally {
      submitBtn.disabled = false;
    }
  });
}

// Nueva evaluación
if (btnNewEval) {
  btnNewEval.addEventListener("click", () => {
    form.reset();

    // Reiniciar campos especiales
    if (stressRange && stressValue) {
      stressRange.value = 3;
      stressValue.textContent = "3";
    }
    if (hiddenSmoke) hiddenSmoke.value = "0";
    if (hiddenAlcohol) hiddenAlcohol.value = "0";
    if (hiddenFamilyHistory) hiddenFamilyHistory.value = "0";
    if (smokeToggle) smokeToggle.checked = false;
    if (alcoholToggle) alcoholToggle.checked = false;
    if (familyHistoryCheckbox) familyHistoryCheckbox.checked = false;

    statusText.textContent = "";
    showView("form-view");
  });
}
