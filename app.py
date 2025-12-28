import streamlit as st
import pandas as pd
import io

from src.domain import (
    resident_scheduling
)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gerador de Escala de Residentes", layout="wide")

# --- ESPAÇO PARA IMAGEM EXTERNA ---
# Substitua a URL abaixo pela URL da imagem do seu hospital ou logo
LOGO_URL = "assets\logo_santa_casa.png"
st.sidebar.image(LOGO_URL)

# --- INTERFACE STREAMLIT ---
st.title("🏥 Sistema de Otimização de Escalas")
st.markdown("Configure os parâmetros na barra lateral e clique em **Gerar Escala**.")

with st.sidebar:
    st.header("⚙️ Configurações")
    ano_input = st.selectbox("Ano", [2025, 2026, 2027, 2028, 2029, 2030], index=1)
    mes_input = st.slider("Mês", 1, 12, 1)
    num_res_input = st.number_input("Total de Residentes", min_value=1, value=12)
    
    r5_input = st.text_input("IDs dos Residentes R5 (separados por vírgula)", "11, 12")
    lista_r5 = [int(i.strip()) for i in r5_input.split(",") if i.strip().isdigit()]

if st.sidebar.button("🚀 Gerar Escala"):
    with st.spinner('Otimizando escala combinatória...'):
        df_escala, df_stats = resident_scheduling(ano_input, mes_input, num_res_input, lista_r5)
    
    if df_escala is not None:
        st.success("Escala gerada com sucesso!")
        
        # Tabs para organizar a visualização
        tab1, tab2 = st.tabs(["📅 Escala de Turnos", "📊 Estatísticas Detalhadas"])
        
        with tab1:
            st.dataframe(df_escala, use_container_width=True)
            
        with tab2:
            st.dataframe(df_stats, use_container_width=True)

        # Preparar Excel em memória
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_escala.to_excel(writer, sheet_name='Escala', index=False)
            df_stats.to_excel(writer, sheet_name='Estatisticas', index=False)
        
        st.download_button(
            label="📥 Baixar Escala em Excel (.xlsx)",
            data=output.getvalue(),
            file_name=f"escala_{mes_input}_{ano_input}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Não foi possível encontrar uma solução viável para estes parâmetros.")
