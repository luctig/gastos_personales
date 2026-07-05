# app.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import plotly.express as px

# ---------- Conexión a Google Sheets ----------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(st.secrets["app"]["sheet_id"])
    return sh.sheet1

COLUMNS = ["id", "fecha", "descripcion", "monto", "categoria", "medio_pago",
           "tarjeta", "cuotas", "moneda", "origen", "notas", "creado_en"]

def leer_df() -> pd.DataFrame:
    ws = get_worksheet()
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["monto"] = pd.to_numeric(df["monto"], errors="coerce").fillna(0)
    df["cuotas"] = pd.to_numeric(df["cuotas"], errors="coerce").fillna(1).astype(int)
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(0).astype(int)
    return df

def proximo_id() -> int:
    df = leer_df()
    return 1 if df.empty else int(df["id"].max()) + 1

def insertar(row: dict):
    ws = get_worksheet()
    nueva = [
        proximo_id(),
        row["fecha"].strftime("%Y-%m-%d"),
        row["descripcion"],
        float(row["monto"]),
        row["categoria"],
        row["medio_pago"],
        row.get("tarjeta", ""),
        int(row.get("cuotas", 1)),
        row.get("moneda", "ARS"),
        row.get("origen", "manual"),
        row.get("notas", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    ws.append_row(nueva, value_input_option="USER_ENTERED")
    st.cache_data.clear()

def eliminar(gasto_id: int):
    ws = get_worksheet()
    data = ws.get_all_records()
    for idx, fila in enumerate(data, start=2):  # +2: fila 1 son headers
        if int(fila.get("id", 0)) == gasto_id:
            ws.delete_rows(idx)
            st.cache_data.clear()
            return True
    return False

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
        monto = c2.number_input(
            "Monto",
            min_value=0.0,
            value=None,
            step=None,
            format="%.2f",
            placeholder="0.00",
        )
        moneda = c3.selectbox("Moneda", ["ARS", "USD"])

        descripcion = st.text_input("Descripción")

        c4, c5, c6 = st.columns(3)
        categoria = c4.selectbox("Categoría", CATEGORIAS)
        medio_pago = c5.selectbox("Medio de pago", MEDIOS_PAGO)
        cuotas = c6.number_input("Cuotas", min_value=1, value=1)

        tarjeta = st.text_input("Tarjeta (opcional)")
        notas = st.text_area("Notas", height=68)

        if st.form_submit_button("Guardar", type="primary"):
            if monto is None or monto <= 0:
                st.error("El monto debe ser mayor a 0")
            elif not descripcion.strip():
                st.error("Ingresá una descripción")
            else:
                try:
                    insertar({"fecha": fecha, "descripcion": descripcion, "monto": monto,
                              "categoria": categoria, "medio_pago": medio_pago,
                              "tarjeta": tarjeta, "cuotas": cuotas, "moneda": moneda,
                              "origen": "manual", "notas": notas})
                    st.success("Gasto guardado ✅")
                except Exception as e:
                    st.error(f"Error al guardar: {e}")

# --- Dashboard ---
with tab_dashboard:
    df = leer_df()
    if df.empty:
        st.info("Todavía no hay gastos cargados. Andá a la pestaña **Carga manual** para empezar.")
    else:
        df["mes"] = df["fecha"].dt.to_period("M").astype(str)

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
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total gastado", f"$ {f['monto'].sum():,.0f}")
            k2.metric("Transacciones", len(f))
            k3.metric("Ticket promedio", f"$ {f['monto'].mean():,.0f}")
            k4.metric("Meses cubiertos", f["mes"].nunique())

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
    if st.button("🔄 Refrescar"):
        st.cache_data.clear()
        st.rerun()

    df = leer_df()
    if df.empty:
        st.info("No hay gastos cargados aún.")
    else:
        df_view = df.sort_values("fecha", ascending=False).copy()
        # Fecha del gasto: solo fecha
        df_view["fecha"] = df_view["fecha"].dt.strftime("%d/%m/%Y")
        # Creado en: solo fecha (era timestamp)
        df_view["creado_en"] = pd.to_datetime(
            df_view["creado_en"], errors="coerce"
        ).dt.strftime("%d/%m/%Y")
        # Monto con formato prolijo
        df_view["monto"] = df_view["monto"].map(lambda x: f"{x:,.2f}")

        st.dataframe(df_view, use_container_width=True, hide_index=True)

        st.download_button("⬇️ Descargar CSV", df.to_csv(index=False).encode(),
                           "gastos.csv", "text/csv")

        with st.expander("🗑️ Eliminar un gasto"):
            id_a_borrar = st.number_input("ID del gasto a eliminar", min_value=1, step=1)
            if st.button("Eliminar", type="secondary"):
                if eliminar(int(id_a_borrar)):
                    st.success(f"Gasto ID {id_a_borrar} eliminado.")
                    st.rerun()
                else:
                    st.error(f"No se encontró un gasto con ID {id_a_borrar}.")
