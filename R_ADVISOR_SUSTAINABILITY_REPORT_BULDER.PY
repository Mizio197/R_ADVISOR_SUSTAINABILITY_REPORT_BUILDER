import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
import base64
from datetime import datetime

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="R-ADVISOR | CSRD Engine", layout="wide", page_icon="🌱")

# --- DATABASE FATTORI DI EMISSIONE (IPCC/GLEC/DEFRA 2025) ---
EMISSION_FACTORS = {
    'transport': {
        'road_truck': 0.062, # kgCO2e/ton-km (Camion refrigerato)
        'sea_freight': 0.012, # kgCO2e/ton-km (Nave Container)
        'air_freight': 1.130  # kgCO2e/ton-km (Aereo - casi urgenti)
    },
    'product_farming': {
        'aglio_it': 0.4,   # kgCO2e/kg (Basso impatto, no riscaldamento)
        'scalogno_ue': 0.5,
        'zenzero_cn': 0.9, # kgCO2e/kg (Alto uso fertilizzanti)
        'zenzero_br': 0.85
    },
    'packaging': {
        'net_plastic': 3.2, # kgCO2e/kg materiale
        'film_pla': 1.8,
        'cartone_fsc': 0.9,
        'cassetta_legno': 0.2
    }
}

# --- CLASSE GENERAZIONE REPORT PDF ---
class CSRDReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'R-ADVISOR - BILANCIO DI SOSTENIBILITA 2026', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()} - Generato da R-ADVISOR Engine', 0, 0, 'C')

def generate_pdf(company_data, materiality_df, ghg_total, scope_breakdown):
    pdf = CSRDReport()
    pdf.add_page()
    
    # Sezione 1: Anagrafica
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Azienda: {company_data['name']}", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f"Settore: {company_data['sector']} | Fornitori Gestiti: {company_data['suppliers']}", 0, 1)
    pdf.ln(5)
    
    # Sezione 2: Performance GHG
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "CALCOLO CARBON FOOTPRINT (Scope 1, 2, 3)", 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f"Totale Emissioni: {ghg_total:.2f} tCO2e", 0, 1)
    for scope, val in scope_breakdown.items():
        pdf.cell(0, 10, f" - {scope}: {val:.2f} tCO2e", 0, 1)
    pdf.ln(5)
    
    # Sezione 3: Doppia Materialità
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "MATRICE DI DOPPIA MATERIALITA' (Top Topics)", 0, 1)
    pdf.set_font('Arial', '', 10)
    for index, row in materiality_df.head(3).iterrows():
        pdf.cell(0, 10, f"- {row['Tema ESRS']}: Impatto {row['Impatto (1-5)']} | Finanziario {row['Finanziaria (1-5)']}", 0, 1)
    
    return pdf.output(dest='S').encode('latin-1')

# --- INTERFACCIA UTENTE (SIDEBAR) ---
st.sidebar.title("R-ADVISOR 🚜")
st.sidebar.info("Enterprise Sustainability Builder")
menu = st.sidebar.radio("Modulo Operativo", ["1. Anagrafica & Config", "2. Data Ingestion (Fornitori)", "3. Doppia Materialità", "4. Calcolo GHG (LCA)", "5. Generazione Report"])

# --- STATO DELL'APPLICAZIONE (SESSION STATE) ---
if 'suppliers_data' not in st.session_state:
    st.session_state.suppliers_data = pd.DataFrame()
if 'company_info' not in st.session_state:
    st.session_state.company_info = {}

# ==============================================================================
# MODULO 1: ANAGRAFICA
# ==============================================================================
if menu == "1. Anagrafica & Config":
    st.title("🏭 Configurazione Aziendale")
    col1, col2 = st.columns(2)
    with col1:
        c_name = st.text_input("Ragione Sociale", "Agri-Food Italia SpA")
        c_piva = st.text_input("Partita IVA", "IT00000000000")
    with col2:
        c_sector = st.selectbox("Settore NACE", ["C10.3 - Lavorazione e conservazione frutta/ortaggi", "Altro"])
        c_employees = st.number_input("Numero Dipendenti (FTE)", value=145)
    
    st.subheader("Parametri Packaging")
    st.caption("Definisci i pesi medi per i formati di vendita (150g - 500g)")
    p_150 = st.slider("Peso imballo per unità 150g (grammi)", 0, 50, 8)
    p_500 = st.slider("Peso imballo per unità 500g (grammi)", 0, 100, 15)
    
    if st.button("Salva Configurazione"):
        st.session_state.company_info = {
            'name': c_name, 'sector': c_sector, 'suppliers': 0, 'pack_150': p_150, 'pack_500': p_500
        }
        st.success("Dati Aziendali Salvati nel Core System.")

# ==============================================================================
# MODULO 2: DATA INGESTION (LA VERA ELABORAZIONE)
# ==============================================================================
elif menu == "2. Data Ingestion (Fornitori)":
    st.title("📦 Gestione Flussi Fornitori")
    st.markdown("Carica il file Excel dei fornitori o inserisci manualmente i lotti di Aglio/Zenzero/Scalogno.")
    
    tab1, tab2 = st.tabs(["Caricamento Massivo", "Inserimento Manuale"])
    
    with tab1:
        uploaded_file = st.file_uploader("Upload File Fornitori (.xlsx, .csv)", type=['xlsx', 'csv'])
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
                st.session_state.suppliers_data = df
                st.success(f"Ingestiti {len(df)} record fornitori.")
            except Exception as e:
                st.error(f"Errore lettura file: {e}")
                
    with tab2:
        with st.form("manual_entry"):
            col1, col2, col3 = st.columns(3)
            with col1:
                f_prod = st.selectbox("Prodotto", ["Aglio", "Scalogno", "Zenzero"])
                f_origin = st.selectbox("Origine", ["Italia", "Spagna (UE)", "Cina (Extra-UE)", "Brasile (Extra-UE)"])
            with col2:
                f_qty = st.number_input("Quantità Lotto (kg)", value=1000)
                f_dist = st.number_input("Distanza Logistica (km)", value=500)
            with col3:
                f_pack = st.selectbox("Tipo Packaging", ["Retina Plastica", "Film PLA", "Cartone FSC"])
                f_trans = st.selectbox("Trasporto", ["Camion", "Nave", "Aereo"])
            
            submit = st.form_submit_button("Aggiungi Lotto al DB")
            
            if submit:
                new_row = {
                    'Prodotto': f_prod, 'Origine': f_origin, 'Qty_kg': f_qty, 
                    'Km': f_dist, 'Packaging': f_pack, 'Trasporto': f_trans
                }
                st.session_state.suppliers_data = pd.concat([st.session_state.suppliers_data, pd.DataFrame([new_row])], ignore_index=True)
                st.success("Lotto registrato.")

    if not st.session_state.suppliers_data.empty:
        st.dataframe(st.session_state.suppliers_data)
        st.session_state.company_info['suppliers'] = len(st.session_state.suppliers_data)

# ==============================================================================
# MODULO 3: DOPPIA MATERIALITA'
# ==============================================================================
elif menu == "3. Doppia Materialità":
    st.title("🧠 Analisi Doppia Materialità")
    st.markdown("Valuta i temi ESRS secondo la prospettiva *Impact Materiality* e *Financial Materiality*.")
    
    topics = ['E1 - Cambiamento Climatico', 'E3 - Risorse Idriche', 'E4 - Biodiversità', 'S1 - Forza Lavoro', 'S2 - Lavoratori nella catena del valore', 'G1 - Condotta']
    
    materiality_data = []
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Valutazione Temi")
        for topic in topics:
            with st.expander(topic):
                imp = st.slider(f"Impatto Socio-Ambientale ({topic})", 1, 5, 3)
                fin = st.slider(f"Rischio/Opp. Finanziaria ({topic})", 1, 5, 3)
                materiality_data.append({'Tema ESRS': topic, 'Impatto (1-5)': imp, 'Finanziaria (1-5)': fin})
    
    df_mat = pd.DataFrame(materiality_data)
    
    with col2:
        st.subheader("Matrice Dinamica")
        # Generazione Grafico Plotly
        fig = px.scatter(df_mat, x="Finanziaria (1-5)", y="Impatto (1-5)", 
                         text="Tema ESRS", size=[20]*len(df_mat), color="Tema ESRS",
                         range_x=[0.5, 5.5], range_y=[0.5, 5.5],
                         title="Soglia di Rilevanza: > 3.0")
        fig.add_shape(type="rect", x0=3, y0=3, x1=5.5, y1=5.5, line=dict(color="Red"), fillcolor="Red", opacity=0.1)
        fig.update_traces(textposition='top center')
        st.plotly_chart(fig, use_container_width=True)
        
    st.session_state.materiality_results = df_mat

# ==============================================================================
# MODULO 4: CALCOLO GHG & LCA (IL CUORE MATEMATICO)
# ==============================================================================
elif menu == "4. Calcolo GHG (LCA)":
    st.title("🧪 Motore di Calcolo LCA")
    
    if st.session_state.suppliers_data.empty:
        st.warning("Nessun dato fornitori caricato. Vai al modulo 2.")
    else:
        df = st.session_state.suppliers_data.copy()
        
        # --- ALGORITMO DI CALCOLO ---
        def calculate_emission(row):
            # 1. Emissioni Agricole (FLAG)
            prod_factor = 0.4 # Default
            if 'Zenzero' in row['Prodotto']: prod_factor = EMISSION_FACTORS['product_farming']['zenzero_cn'] if 'Cina' in row['Origine'] else EMISSION_FACTORS['product_farming']['zenzero_br']
            elif 'Aglio' in row['Prodotto']: prod_factor = EMISSION_FACTORS['product_farming']['aglio_it']
            
            flag_emission = row['Qty_kg'] * prod_factor
            
            # 2. Emissioni Trasporto (Scope 3 Upstream)
            trans_type = 'road_truck'
            if 'Nave' in row['Trasporto']: trans_type = 'sea_freight'
            elif 'Aereo' in row['Trasporto']: trans_type = 'air_freight'
            
            # Formula: (Kg / 1000) * Km * Factor
            transport_emission = (row['Qty_kg'] / 1000) * row['Km'] * EMISSION_FACTORS['transport'][trans_type]
            
            # 3. Emissioni Packaging
            # Assumiamo mix 50% formato 150g e 50% formato 500g per semplicità di demo
            pack_factor = EMISSION_FACTORS['packaging']['net_plastic'] 
            if 'Cartone' in row['Packaging']: pack_factor = EMISSION_FACTORS['packaging']['cartone_fsc']
            
            # Peso imballo (kg totali imballo)
            total_pack_weight_kg = (row['Qty_kg'] * 0.02) # Stima 2% peso imballo su peso netto
            pack_emission = total_pack_weight_kg * pack_factor
            
            return pd.Series([flag_emission, transport_emission, pack_emission])

        # Applicazione calcolo
        df[['GHG_Agri', 'GHG_Transport', 'GHG_Pack']] = df.apply(calculate_emission, axis=1)
        df['Total_CO2e'] = df['GHG_Agri'] + df['GHG_Transport'] + df['GHG_Pack']
        
        # --- VISUALIZZAZIONE RISULTATI ---
        total_co2 = df['Total_CO2e'].sum() / 1000 # in Tonnellate
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Carbon Footprint Totale", f"{total_co2:.2f} tCO2e", delta_color="inverse")
        col2.metric("Media per kg Prodotto", f"{(df['Total_CO2e'].sum() / df['Qty_kg'].sum()):.2f} kgCO2e/kg")
        col3.metric("Lotti Analizzati", len(df))
        
        st.subheader("Breakdown Emissioni")
        chart_data = df[['GHG_Agri', 'GHG_Transport', 'GHG_Pack']].sum().reset_index()
        chart_data.columns = ['Categoria', 'Emissioni (kgCO2e)']
        
        fig = px.pie(chart_data, values='Emissioni (kgCO2e)', names='Categoria', 
                     color_discrete_sequence=['#2ecc71', '#f1c40f', '#e74c3c'])
        st.plotly_chart(fig)
        
        st.subheader("Dettaglio Analitico")
        st.dataframe(df.style.format("{:.2f}", subset=['GHG_Agri', 'GHG_Transport', 'GHG_Pack', 'Total_CO2e']))
        
        # Store for report
        st.session_state.ghg_results = {
            'total': total_co2,
            'breakdown': {
                'Scope 3 (Agricoltura/FLAG)': df['GHG_Agri'].sum() / 1000,
                'Scope 3 (Logistica)': df['GHG_Transport'].sum() / 1000,
                'Scope 3 (Packaging)': df['GHG_Pack'].sum() / 1000
            }
        }

# ==============================================================================
# MODULO 5: GENERAZIONE REPORT
# ==============================================================================
elif menu == "5. Generazione Report":
    st.title("📄 Export Bilancio di Sostenibilità")
    
    if 'ghg_results' not in st.session_state or 'materiality_results' not in st.session_state:
        st.error("Completa prima le fasi di Analisi Materialità e Calcolo GHG.")
    else:
        st.success("Tutti i dati sono pronti per l'elaborazione.")
        
        if st.button("GENERA REPORT PDF"):
            # Generazione PDF
            pdf_bytes = generate_pdf(
                st.session_state.company_info,
                st.session_state.materiality_results,
                st.session_state.ghg_results['total'],
                st.session_state.ghg_results['breakdown']
            )
            
            b64 = base64.b64encode(pdf_bytes).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="R-ADVISOR_Report_2026.pdf" style="padding:10px; background-color:#4CAF50; color:white; text-decoration:none; border-radius:5px;">SCARICA REPORT PDF UFFICIALE</a>'
            st.markdown(href, unsafe_allow_html=True)
            
            st.info("Il report include i KPI richiesti dalla direttiva CSRD per il settore Agroalimentare.")
