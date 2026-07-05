# app.py
import streamlit as st
import pandas as pd
import sqlite3
import pdfplumber
import re
from datetime import date, datetime
import plotly.express as px

DB = "gastos.db"

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            descripcion TEXT,
            monto REAL NOT NULL,
            categoria TEXT,
            medio_pago TEXT,
            tarjeta TEXT,
            cuotas INTEGER DEFAULT 1,
            moneda TEXT DEFAULT 'ARS',
            origen TEXT,
            archivo_origen TEXT,
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn

def insertar(row: dict):
    conn = get_conn()
    conn.execute("""INSERT INTO gastos (fecha, descripcion, monto, categoria,
                    medio_pago, tarjeta, cuotas, moneda, origen, archivo_origen, notas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (row["fecha"], row["descripcion"], row["monto"], row["categoria"],
                  row["medio_pago"], row.get("tarjeta"), row.get("cuotas",1),
                  row.get("moneda","ARS"), row["origen"], row.get("archivo_origen"),
                  row.get("notas")))
    conn.commit(); conn.close()

def leer_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM gastos", conn, parse_dates=["fecha"])
    conn.close()
    return df

# ---------- PDF PARSER ----------
CATEGORIAS = ["Supermercado","Transporte","Ocio","Salud","Servicios",
              "Restaurantes","Educación","Hogar","Vestimenta","Otros"]

def parsear_pdf(file, tarjeta_default="") -> pd.DataFrame:
    """Extrae líneas típicas de resumen de tarjeta: fecha  descripción  monto"""
    filas = []
    with pdfplumber.open(file) as pdf:
        texto = "\n".join([p.extract_text() or "" for p in pdf.pages])

    # regex adaptable: dd/mm/yy(yy)   descripción   monto (formato AR con . miles y , decimales)
    patron = re.compile(
        r"(\d{2}/\d{2}/\d{2,4})\s+(.+?)\s+([\-]?[\d\.]+,\d{2})"
    )
    for m in patron.finditer(texto):
        fecha_str, desc, monto_str = m.groups()
        try:
            fecha = datetime.strptime(fecha_str, "%d/%m/%y").date() \
                    if len(fecha_str)==8 else datetime.strptime(fecha_str,"%d/%m/%Y").date()
        except:
            continue
        monto = float(monto_str.replace(".","").replace(",","."))
        filas.append({
            "fecha": fecha, "descripcion": desc.strip(), "monto": monto,
            "categoria": "Otros", "medio_pago": "Tarjeta crédito",
            "tarjeta": tarjeta_default, "cuotas": 1, "moneda":"ARS",
            "origen":"pdf"
        })
    return pd.DataFrame(filas)

# ---------- UI ----------
st.set_page_config(page_title="Mis Gastos", layout="wide", page_icon="💰")
st.title("💰 Control de Gastos Personales")

tab_registro, tab_pdf, tab_dashboard, tab_datos = st.tabs(
    ["➕ Carga manual", "📄 Importar PDF", "📊 Dashboard", "🗃️ Datos"])

# --- Carga manual ---
with tab_registro:
    with st.form("form_gasto", clear_on_submit=True):
        c1,c2,c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=date.today())
        monto = c2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
        moneda = c3.selectbox("Moneda", ["ARS","USD"])
        descripcion = st.text_input("Descripción")
        c4,c5,c6 = st.columns(3)
        categoria = c4.selectbox("Categoría", CATEGORIAS)
        medio_pago = c5.selectbox("Medio de pago",
            ["Tarjeta crédito","Tarjeta débito","Efectivo","Transferencia","Buepp/QR","Débito automático"])
        cuotas = c6.number_input("Cuotas", min_value=1, value=1)
        tarjeta = st.text_input("Tarjeta (opcional)")
        notas = st.text_area("Notas", height=68)
        if st.form_submit_button("Guardar", type="primary"):
            insertar({"fecha":fecha,"descripcion":descripcion,"monto":monto,
                      "categoria":categoria,"medio_pago":medio_pago,"tarjeta":tarjeta,
                      "cuotas":cuotas,"moneda":moneda,"origen":"manual","notas":notas})
            st.success("Gasto guardado ✅")

# --- PDF ---
with tab_pdf:
    st.info("Subí resúmenes de tarjeta o comprobantes. Revisá y editá antes de confirmar.")
    tarjeta_default = st.text_input("Tarjeta asociada a este PDF", "Visa Ciudad")
    archivo = st.file_uploader("Elegí un PDF", type=["pdf"])
    if archivo:
        df_pdf = parsear_pdf(archivo, tarjeta_default)
        if df_pdf.empty:
            st.warning("No pude detectar movimientos con el patrón por defecto. Contame el formato y ajustamos el regex.")
        else:
            st.write(f"Se detectaron **{len(df_pdf)}** movimientos. Editá lo que necesites:")
            edit = st.data_editor(df_pdf, num_rows="dynamic", use_container_width=True,
                column_config={
                    "categoria": st.column_config.SelectboxColumn(options=CATEGORIAS),
                    "medio_pago": st.column_config.SelectboxColumn(
                        options=["Tarjeta crédito","Tarjeta débito","Efectivo","Transferencia","Buepp/QR"])
                })
            if st.button("Confirmar e importar", type="primary"):
                for _, r in edit.iterrows():
                    row = r.to_dict()
                    row["archivo_origen"] = archivo.name
                    insertar(row)
                st.success(f"Importados {len(edit)} gastos ✅")

# --- Dashboard ---
with tab_dashboard:
    df = leer_df()
    if df.empty:
        st.info("Todavía no hay gastos cargados.")
    else:
        df["mes"] = df["fecha"].dt.to_period("M").astype(str)
        # Filtros
        with st.sidebar:
            st.header("🔎 Filtros")
            meses = st.multiselect("Mes", sorted(df["mes"].unique(), reverse=True))
            cats  = st.multiselect("Categoría", sorted(df["categoria"].dropna().unique()))
            medios= st.multiselect("Medio de pago", sorted(df["medio_pago"].dropna().unique()))
            tarj  = st.multiselect("Tarjeta", sorted(df["tarjeta"].dropna().unique()))

        f = df.copy()
        if meses:  f = f[f["mes"].isin(meses)]
        if cats:   f = f[f["categoria"].isin(cats)]
        if medios: f = f[f["medio_pago"].isin(medios)]
        if tarj:   f = f[f["tarjeta"].isin(tarj)]

        # KPIs
        k1,k2,k3,k4 = st.columns(4)
        k1.metric("Total gastado", f"$ {f['monto'].sum():,.0f}")
        k2.metric("Transacciones", len(f))
        k3.metric("Ticket promedio", f"$ {f['monto'].mean():,.0f}" if len(f) else "-")
        k4.metric("Meses cubiertos", f["mes"].nunique())

        # Gráficos
        c1,c2 = st.columns(2)
        with c1:
            st.subheader("Evolución mensual")
            g = f.groupby("mes",as_index=False)["monto"].sum()
            st.plotly_chart(px.bar(g, x="mes", y="monto"), use_container_width=True)
        with c2:
            st.subheader("Por categoría")
            g = f.groupby("categoria",as_index=False)["monto"].sum()
            st.plotly_chart(px.pie(g, names="categoria", values="monto", hole=.4),
                            use_container_width=True)

        st.subheader("Por medio de pago")
        g = f.groupby("medio_pago",as_index=False)["monto"].sum().sort_values("monto",ascending=False)
        st.plotly_chart(px.bar(g, x="medio_pago", y="monto"), use_container_width=True)

# --- Datos crudos ---
with tab_datos:
    df = leer_df()
    st.dataframe(df, use_container_width=True)
    st.download_button("⬇️ Descargar CSV", df.to_csv(index=False).encode(),
                       "gastos.csv","text/csv")
