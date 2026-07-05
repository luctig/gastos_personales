# app.py
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
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
            notas TEXT,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn

def insertar(row: dict):
    conn = get_conn()
    conn.execute("""INSERT INTO gastos (fecha, descripcion, monto, categoria,
                    medio_pago, tarjeta, cuotas, moneda, origen, notas)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (row["fecha"], row["descripcion"], row["monto"], row["categoria"],
                  row["medio_pago"], row.get("tarjeta"), row.get("cuotas", 1),
                  row.get("moneda", "ARS"), row["origen"], row.get("notas")))
    conn.commit(); conn.close()

def eliminar(gasto_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
    conn.commit(); conn.close()

def leer_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM gastos", conn, parse_dates=["fecha"])
    conn.close()
    return df

# ---------- Constantes ----------
CATEGORIAS = ["Supermercado", "Transporte", "Ocio", "Salud", "Servicios",
              "Restaurantes", "Educación", "Hogar", "Vestimenta", "Otros"]

MEDIOS_PAGO = ["Tarjeta crédito", "Tarjeta débito", "Efectivo",
               "Transferencia", "Buepp/QR", "Débito automático"]

# ---------- UI ----------
st.set_page_config(page_title="Mis Gastos", layout="wide", page_icon="💰")
st.title("💰 Control de Gastos Personales")

tab_registro, tab_dashboard, tab_datos = st.tabs(
    ["➕ Carga manual", "📊 Dashboard", "🗃️ Datos"])

# --- Carga manual ---
with tab_registro:
    with st.form("form_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        fecha = c1.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
        monto = c2.number_input("Monto", min_value=0.0, step=100.0, format="%.2f")
        moneda = c3.selectbox("Moneda", ["ARS", "USD"])

        descripcion = st.text_input("Descripción")

        c4, c5, c6 = st.columns(3)
        categoria = c4.selectbox("Categoría", CATEGORIAS)
        medio_pago = c5.selectbox("Medio de pago", MEDIOS_PAGO)
        cuotas = c6.number_input("Cuotas", min_value=1, value=1)

        tarjeta = st.text_input("Tarjeta (opcional)")
        notas = st.text_area("Notas", height=68)

        if st.form_submit_button("Guardar", type="primary"):
            if monto <= 0:
                st.error("El monto debe ser mayor a 0")
            elif not descripcion.strip():
                st.error("Ingresá una descripción")
            else:
                insertar({"fecha": fecha, "descripcion": descripcion, "monto": monto,
                          "categoria": categoria, "medio_pago": medio_pago,
                          "tarjeta": tarjeta, "cuotas": cuotas, "moneda": moneda,
                          "origen": "manual", "notas": notas})
                st.success("Gasto guardado ✅")

# --- Dashboard ---
with tab_dashboard:
    df = leer_df()
    if df.empty:
        st.info("Todavía no hay gastos cargados. Andá a la pestaña **Carga manual** para empezar.")
    else:
        df["mes"] = df["fecha"].dt.to_period("M").astype(str)

        # Filtros
        with st.sidebar:
            st.header("🔎 Filtros")
            meses = st.multiselect("Mes", sorted(df["mes"].unique(), reverse=True))
            cats = st.multiselect("Categoría", sorted(df["categoria"].dropna().unique()))
            medios = st.multiselect("Medio de pago", sorted(df["medio_pago"].dropna().unique()))
            tarj_opts = sorted([t for t in df["tarjeta"].dropna().unique() if t])
            tarj = st.multiselect("Tarjeta", tarj_opts) if tarj_opts else []
            monedas = st.multiselect("Moneda", sorted(df["moneda"].dropna().unique()))

        f = df.copy()
        if meses:   f = f[f["mes"].isin(meses)]
        if cats:    f = f[f["categoria"].isin(cats)]
        if medios:  f = f[f["medio_pago"].isin(medios)]
        if tarj:    f = f[f["tarjeta"].isin(tarj)]
        if monedas: f = f[f["moneda"].isin(monedas)]

        if f.empty:
            st.warning("No hay gastos que coincidan con los filtros.")
        else:
            # KPIs
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total gastado", f"$ {f['monto'].sum():,.0f}")
            k2.metric("Transacciones", len(f))
            k3.metric("Ticket promedio", f"$ {f['monto'].mean():,.0f}")
            k4.metric("Meses cubiertos", f["mes"].nunique())

            # Gráficos
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Evolución mensual")
                g = f.groupby("mes", as_index=False)["monto"].sum().sort_values("mes")
                st.plotly_chart(px.bar(g, x="mes", y="monto"), use_container_width=True)
            with c2:
                st.subheader("Por categoría")
                g = f.groupby("categoria", as_index=False)["monto"].sum()
                st.plotly_chart(px.pie(g, names="categoria", values="monto", hole=.4),
                                use_container_width=True)

            st.subheader("Por medio de pago")
            g = f.groupby("medio_pago", as_index=False)["monto"].sum().sort_values("monto", ascending=False)
            st.plotly_chart(px.bar(g, x="medio_pago", y="monto"), use_container_width=True)

# --- Datos crudos ---
with tab_datos:
    df = leer_df()
    if df.empty:
        st.info("No hay gastos cargados aún.")
    else:
        st.dataframe(df.sort_values("fecha", ascending=False), use_container_width=True)

        st.download_button("⬇️ Descargar CSV", df.to_csv(index=False).encode(),
                           "gastos.csv", "text/csv")

        with st.expander("🗑️ Eliminar un gasto"):
            id_a_borrar = st.number_input("ID del gasto a eliminar", min_value=1, step=1)
            if st.button("Eliminar", type="secondary"):
                eliminar(int(id_a_borrar))
                st.success(f"Gasto ID {id_a_borrar} eliminado. Refrescá la pestaña.")
