"""
Simulador de un tren epicicloidal simple (planeta, satélites, corona y portasatélites).

Notación de la clase «La caja de cambios automática»:
    1   planeta (solar)          z1, ω1
    2   corona (dentado interior) z2, ω2
    ps  portasatélites            ωps
    12ps satélite                 zs, ω12ps (relativa al portasatélites)

Ecuación de Willis:  (ω1 - ωps) / (ω2 - ωps) = -z2 / z1

Ejecutar con:   streamlit run tren_epicicloidal.py
"""

import json
import math

import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Tren epicicloidal", layout="wide")

ELEMENTOS = {"planeta": "Planeta (1)", "corona": "Corona (2)", "ps": "Portasatélites (ps)"}
CORTO = {"planeta": "Planeta", "corona": "Corona", "ps": "ps"}
COLORES = {"planeta": "#466ec8", "corona": "#c828b4", "ps": "#787878", "satelite": "#f0c828"}


# ---------------------------------------------------------------------------
#  Cinemática
# ---------------------------------------------------------------------------
def velocidades(z1, z2, zs, fijo, entrada, w_in):
    """Velocidades absolutas (en las unidades de w_in) de los tres ejes y del satélite.

    Se impone ω_fijo = 0, ω_entrada = w_in y se despeja el tercero con Willis:
        ω1 - ωps = -(z2/z1) (ω2 - ωps)   ⇔   z1 ω1 + z2 ω2 = (z1 + z2) ωps
    """
    w = {fijo: 0.0, entrada: w_in}
    salida = ({"planeta", "corona", "ps"} - {fijo, entrada}).pop()
    if salida == "ps":
        w["ps"] = (z1 * w["planeta"] + z2 * w["corona"]) / (z1 + z2)
    elif salida == "planeta":
        w["planeta"] = ((z1 + z2) * w["ps"] - z2 * w["corona"]) / z1
    else:
        w["corona"] = ((z1 + z2) * w["ps"] - z1 * w["planeta"]) / z2
    # satélite: velocidad relativa al portasatélites y absoluta
    w_rel = -(w["planeta"] - w["ps"]) * z1 / zs
    w["sat_rel"] = w_rel
    w["sat_abs"] = w["ps"] + w_rel
    return w, salida


def relacion(z1, z2, fijo, entrada):
    """Relación de transmisión i = ω_entrada / ω_salida."""
    w, salida = velocidades(z1, z2, (z2 - z1) / 2, fijo, entrada, 1.0)
    return 1.0 / w[salida], salida


def tipo_relacion(i):
    if i < 0:
        return "inversora (cambia el sentido de giro)"
    if abs(i - 1) < 1e-9:
        return "directa"
    return "reductora (multiplica el par)" if i > 1 else "multiplicadora (overdrive)"


# ---------------------------------------------------------------------------
#  Interfaz: parámetros
# ---------------------------------------------------------------------------
st.sidebar.header("Geometría")
z1 = st.sidebar.slider("Dientes del planeta  z₁", 12, 60, 30)
zs = st.sidebar.slider("Dientes del satélite  zₛ", 10, 40, 21)
z2 = z1 + 2 * zs
st.sidebar.markdown(f"Dientes de la corona: **z₂ = z₁ + 2 zₛ = {z2}**")
n_sat = st.sidebar.slider("Número de satélites", 1, 6, 3)
montable = (z1 + z2) % n_sat == 0
if not montable:
    st.sidebar.warning(
        f"(z₁ + z₂)/N = {z1 + z2}/{n_sat} no es entero: los satélites no pueden "
        "montarse equiespaciados (algunos no engranarán bien en el dibujo)."
    )

st.sidebar.header("Condición de funcionamiento")
fijo = st.sidebar.radio("Elemento fijo", list(ELEMENTOS), format_func=ELEMENTOS.get)
libres = [e for e in ELEMENTOS if e != fijo]
entrada = st.sidebar.radio("Entrada (motor)", libres, format_func=ELEMENTOS.get)
n_in = st.sidebar.number_input("Velocidad de entrada (rpm)", value=1000.0, step=100.0)
m_in = st.sidebar.number_input("Par de entrada (N·m)", value=100.0, step=10.0)

st.sidebar.header("Animación")
vel_anim = st.sidebar.slider("Velocidad de la animación", 0.1, 3.0, 1.0, 0.1)

w, salida = velocidades(z1, z2, zs, fijo, entrada, n_in)
i = n_in / w[salida] if w[salida] != 0 else math.inf
m_out = m_in * i            # par entregado a la carga (sin pérdidas)
m_reac = m_in * (i - 1)     # par de reacción sobre el elemento fijo

# ---------------------------------------------------------------------------
#  Cabecera
# ---------------------------------------------------------------------------
st.title("Tren epicicloidal simple")
st.caption(
    f"Fijo: **{ELEMENTOS[fijo]}** · Entrada: **{ELEMENTOS[entrada]}** · "
    f"Salida: **{ELEMENTOS[salida]}**"
)

col_anim, col_res = st.columns([1.15, 1])

# ---------------------------------------------------------------------------
#  Animación (canvas + JavaScript)
# ---------------------------------------------------------------------------
param = {
    "z1": z1, "z2": z2, "zs": zs, "n": n_sat,
    # velocidades normalizadas: la entrada gira a 1 rad/s en la animación
    "w1": w["planeta"] / n_in if n_in else 0.0,
    "w2": w["corona"] / n_in if n_in else 0.0,
    "wps": w["ps"] / n_in if n_in else 0.0,
    "wsat": w["sat_abs"] / n_in if n_in else 0.0,
    "anim": vel_anim * (1 if n_in >= 0 else -1),
    "fijo": fijo, "entrada": entrada, "salida": salida,
    "col": COLORES,
}

HTML = r"""
<div style="font-family:sans-serif">
  <canvas id="c" width="560" height="560" style="max-width:100%"></canvas>
  <div style="margin-top:4px">
    <button id="bp">Pausa</button> <button id="br">Reiniciar</button>
    <span style="font-size:12px;color:#666;margin-left:8px">
      Rayas blancas: referencia para ver el giro de cada elemento.</span>
  </div>
</div>
<script>
const P = __PARAM__;
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const W = cv.width, H = cv.height, R = 252;           // radio exterior disponible
const m = R / (P.z2 / 2 + 4.2);                        // módulo en píxeles
const r1 = m * P.z1 / 2, r2 = m * P.z2 / 2, rs = m * P.zs / 2, rc = r1 + rs;
const TAU = 2 * Math.PI;
const frac = x => x - Math.floor(x);

// --- fases iniciales para que los dientes engranen -------------------------
const phi = [...Array(P.n).keys()].map(k => TAU * k / P.n);
const psi = phi.map(f => {                              // fase de cada satélite
  const s = frac(f * P.z1 / TAU);                       // fase del planeta en el contacto
  return f + Math.PI - (0.5 - s) * TAU / P.zs;
});
const q = frac((phi[0] - psi[0]) * P.zs / TAU);         // satélite 0 en el contacto exterior
const psiR = phi[0] - (q + 0.5) * TAU / P.z2;           // fase de la corona

function gear(z, r, rot, internal, nuevo = true) {                    // contorno dentado (dientes centrados en rot + 2πj/z)
  const p = TAU / z, ha = m, hf = 1.25 * m;
  const tip = internal ? r - ha : r + ha, root = internal ? r + hf : r - hf;
  if (nuevo) ctx.beginPath();
  for (let j = 0; j < z; j++) {
    const a = rot + j * p;
    const pts = [[root, a - 0.5 * p], [root, a - 0.27 * p], [tip, a - 0.13 * p],
                 [tip, a + 0.13 * p], [root, a + 0.27 * p]];
    pts.forEach(([rr, aa], k) => {
      const x = rr * Math.cos(aa), y = rr * Math.sin(aa);
      (j === 0 && k === 0) ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
  }
  ctx.closePath();
}

function hatch(alpha) {                                  // trama para el elemento fijo
  const c = document.createElement('canvas'); c.width = c.height = 8;
  const g = c.getContext('2d'); g.strokeStyle = `rgba(0,0,0,${alpha})`; g.lineWidth = 1;
  g.beginPath(); g.moveTo(0, 8); g.lineTo(8, 0); g.stroke();
  return ctx.createPattern(c, 'repeat');
}
const pat = hatch(0.35);

function label(txt, x, y, color) {
  ctx.save(); ctx.scale(1, -1);
  ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center';
  ctx.lineWidth = 4; ctx.strokeStyle = 'white'; ctx.strokeText(txt, x, -y);
  ctx.fillStyle = color; ctx.fillText(txt, x, -y);
  ctx.restore();
}
const tag = e => e === P.fijo ? 'FIJO' : (e === P.entrada ? 'ENTRADA' : 'SALIDA');
const tagCol = e => e === P.fijo ? '#555' : (e === P.entrada ? '#d21e1e' : '#415fd7');

let t = 0, run = true, last = null;
document.getElementById('bp').onclick = e => { run = !run; e.target.textContent = run ? 'Pausa' : 'Seguir'; };
document.getElementById('br').onclick = () => { t = 0; };

function draw() {
  const th1 = P.w1 * t, th2 = P.w2 * t, thc = P.wps * t, ths = P.wsat * t;
  ctx.setTransform(1, 0, 0, -1, W / 2, H / 2);          // y hacia arriba, giro antihorario positivo
  ctx.clearRect(-W, -H, 2 * W, 2 * H);

  // corona
  ctx.beginPath(); ctx.moveTo(r2 + 4 * m, 0); ctx.arc(0, 0, r2 + 4 * m, 0, TAU); ctx.closePath();
  gear(P.z2, r2, th2 + psiR, true, false);
  ctx.fillStyle = P.col.corona; ctx.fill('evenodd');
  if (P.fijo === 'corona') { ctx.fillStyle = pat; ctx.fill('evenodd'); }
  ctx.lineWidth = 1; ctx.strokeStyle = '#333'; ctx.stroke();
  ctx.strokeStyle = 'white'; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo((r2 + 1.4 * m) * Math.cos(th2), (r2 + 1.4 * m) * Math.sin(th2));
  ctx.lineTo((r2 + 3.8 * m) * Math.cos(th2), (r2 + 3.8 * m) * Math.sin(th2)); ctx.stroke();

  // satélites
  phi.forEach((f, k) => {
    const cx = rc * Math.cos(f + thc), cy = rc * Math.sin(f + thc);
    ctx.save(); ctx.translate(cx, cy);
    gear(P.zs, rs, ths + psi[k], false);   // fase absoluta del satélite k
    ctx.fillStyle = P.col.satelite; ctx.fill(); ctx.lineWidth = 1; ctx.strokeStyle = '#333'; ctx.stroke();
    ctx.strokeStyle = 'white'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0.75 * rs * Math.cos(ths + psi[k]), 0.75 * rs * Math.sin(ths + psi[k])); ctx.stroke();
    ctx.fillStyle = P.col.ps; ctx.beginPath(); ctx.arc(0, 0, 0.18 * rs, 0, TAU); ctx.fill();
    if (P.fijo === 'ps') { ctx.fillStyle = pat; ctx.beginPath(); ctx.arc(0, 0, 0.18 * rs, 0, TAU); ctx.fill(); }
    ctx.restore();
  });

  // planeta
  gear(P.z1, r1, th1, false);
  ctx.fillStyle = P.col.planeta; ctx.fill();
  if (P.fijo === 'planeta') { ctx.fillStyle = pat; ctx.fill(); }
  ctx.lineWidth = 1; ctx.strokeStyle = '#333'; ctx.stroke();
  ctx.strokeStyle = 'white'; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0.8 * r1 * Math.cos(th1), 0.8 * r1 * Math.sin(th1)); ctx.stroke();

  // portasatélites: brazos y cubo, dibujados por encima (como una placa transparente)
  ctx.lineCap = 'round'; ctx.globalAlpha = 0.85;
  phi.forEach(f => {
    ctx.strokeStyle = P.col.ps; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(rc * Math.cos(f + thc), rc * Math.sin(f + thc)); ctx.stroke();
    if (P.fijo === 'ps') { ctx.strokeStyle = pat; ctx.stroke(); }
    ctx.fillStyle = P.col.ps; ctx.beginPath();
    ctx.arc(rc * Math.cos(f + thc), rc * Math.sin(f + thc), 0.2 * rs, 0, TAU); ctx.fill();
  });
  ctx.globalAlpha = 1;
  ctx.fillStyle = P.col.ps; ctx.beginPath(); ctx.arc(0, 0, 0.22 * r1, 0, TAU); ctx.fill();
  if (P.fijo === 'ps') { ctx.fillStyle = pat; ctx.fill(); }

  // rótulos
  label('Planeta: ' + tag('planeta'), 0, -0.45 * r1, tagCol('planeta'));
  label('Corona: ' + tag('corona'), 0, -(r2 + 4 * m) - 16, tagCol('corona'));
  const fl = phi[0] + thc;
  label('ps: ' + tag('ps'), 0.55 * rc * Math.cos(fl) + 0, 0.55 * rc * Math.sin(fl) + 14, tagCol('ps'));
}

function loop(ts) {
  if (last !== null && run) t += (ts - last) / 1000 * P.anim;
  last = ts; draw(); requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
</script>
"""

def incrustar_html(html, alto):
    """st.iframe en versiones recientes de Streamlit; components.html en las antiguas."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=alto)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=alto)


with col_anim:
    incrustar_html(HTML.replace("__PARAM__", json.dumps(param)), 610)

# ---------------------------------------------------------------------------
#  Resultados
# ---------------------------------------------------------------------------
def rpm(x):
    return f"{x:,.1f} rpm".replace(",", " ").replace(".", ",")


with col_res:
    st.subheader("Velocidades")
    c1, c2 = st.columns(2)
    c1.metric("Planeta  ω₁", rpm(w["planeta"]))
    c2.metric("Corona  ω₂", rpm(w["corona"]))
    c1.metric("Portasatélites  ωps", rpm(w["ps"]))
    c2.metric("Satélite (absoluta)", rpm(w["sat_abs"]))
    st.caption(f"Velocidad del satélite relativa al portasatélites: ω₁₂ps = {rpm(w['sat_rel'])}")

    st.subheader("Relación de transmisión")
    st.markdown(
        f"$i = \\dfrac{{\\omega_{{entrada}}}}{{\\omega_{{salida}}}} = "
        f"\\mathbf{{{i:.3f}}}$".replace(".", "{,}") + f"  —  {tipo_relacion(i)}"
    )

    st.subheader("Pares (sin pérdidas)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Entrada", f"{m_in:.0f} N·m")
    c2.metric("Salida", f"{m_out:.0f} N·m")
    c3.metric("Reacción (fijo)", f"{m_reac:.0f} N·m")
    st.caption(
        "Potencia: M_entrada·ω_entrada = M_salida·ω_salida. "
        "Equilibrio: M_entrada + M_reacción = M_salida (la carcasa absorbe la diferencia)."
    )

# ---------------------------------------------------------------------------
#  Willis con los números sustituidos
# ---------------------------------------------------------------------------
st.subheader("Ecuación de Willis")
sym = {"planeta": r"\omega_1", "corona": r"\omega_2", "ps": r"\omega_{ps}"}
val = {e: (r"0" if e == fijo else (f"{n_in:g}" if e == entrada else sym[e])) for e in ELEMENTOS}
st.latex(r"\frac{\omega_1-\omega_{ps}}{\omega_2-\omega_{ps}} = -\frac{z_2}{z_1}"
         r"\quad\Longleftrightarrow\quad z_1\,\omega_1 + z_2\,\omega_2 = (z_1+z_2)\,\omega_{ps}")
st.latex(
    f"{z1}\\cdot {val['planeta']} + {z2}\\cdot {val['corona']} = {z1 + z2}\\cdot {val['ps']}"
    f"\\quad\\Rightarrow\\quad {sym[salida]} = {w[salida]:.2f}\\ \\text{{rpm}}".replace(".", "{,}")
)
formulas = {
    ("corona", "planeta"): r"i = 1 + \frac{z_2}{z_1}",
    ("corona", "ps"): r"i = \frac{z_1}{z_1+z_2}",
    ("ps", "planeta"): r"i = -\frac{z_2}{z_1}",
    ("ps", "corona"): r"i = -\frac{z_1}{z_2}",
    ("planeta", "corona"): r"i = \frac{z_1+z_2}{z_2} = 1 + \frac{z_1}{z_2}",
    ("planeta", "ps"): r"i = \frac{z_2}{z_1+z_2}",
}
st.latex(formulas[(fijo, entrada)] + f" = {i:.3f}".replace(".", "{,}"))

# ---------------------------------------------------------------------------
#  Diagrama de palanca y tabla de los seis casos
# ---------------------------------------------------------------------------
col_pal, col_tab = st.columns([1, 1.1])

with col_pal:
    st.subheader("Analogía de la palanca")
    pos = {"corona": 0.0, "ps": float(z1), "planeta": float(z1 + z2)}   # corona–ps ∝ z1, ps–planeta ∝ z2
    fig, ax = plt.subplots(figsize=(5, 4.2))
    ax.axvline(0, color="0.6", lw=0.8)
    ax.plot([0, 0], [0, z1 + z2], color="0.5", lw=5, solid_capstyle="round", zorder=1)
    vmax = max(abs(w[e]) for e in ELEMENTOS) or 1
    for e, y in pos.items():
        ax.plot(0, y, "o", color=COLORES[e], ms=10, zorder=3)
        ax.annotate("", xy=(w[e], y), xytext=(0, y),
                    arrowprops=dict(arrowstyle="-|>", color=COLORES[e], lw=2.2))
        ax.text(-0.04 * vmax, y, ELEMENTOS[e] + ("  (fijo)" if e == fijo else ""),
                ha="right", va="center", color=COLORES[e], fontsize=9)
    ys = [pos[e] for e in ("corona", "ps", "planeta")]
    xs = [w[e] for e in ("corona", "ps", "planeta")]
    ax.plot(xs, ys, "--", color="#d21e1e", lw=1.2)
    ax.set_xlim(-1.9 * vmax, 1.25 * vmax)
    ax.set_ylim(-0.08 * (z1 + z2), 1.08 * (z1 + z2))
    ax.set_yticks([])
    ax.set_xlabel("velocidad de giro (rpm)")
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    st.pyplot(fig)
    st.caption("Distancias: corona–portasatélites ∝ z₁ y portasatélites–planeta ∝ z₂. "
               "Las velocidades de los tres ejes quedan sobre una recta.")

with col_tab:
    st.subheader("Los seis casos con un elemento fijo")
    filas = []
    for f in ELEMENTOS:
        for e in ELEMENTOS:
            if e == f:
                continue
            ii, s = relacion(z1, z2, f, e)
            filas.append({
                "Fijo": CORTO[f], "Entrada": CORTO[e], "Salida": CORTO[s],
                "i": f"{ii:.3f}".replace(".", ","), "Tipo": tipo_relacion(ii).split(" (")[0],
                "": "◀" if (f, e) == (fijo, entrada) else "",
            })
    try:
        st.dataframe(filas, hide_index=True, width="stretch")
    except Exception:                       # versiones antiguas de Streamlit
        st.dataframe(filas, hide_index=True, use_container_width=True)
    st.caption("Si se unen dos elementos con un embrague, todo el tren gira como un "
               "sólido rígido: directa, i = 1.")
