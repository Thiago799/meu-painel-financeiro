import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from dateutil.relativedelta import relativedelta

# --- 1. CONFIGURAÇÃO DA PÁGINA (Sempre a primeira linha) ---
st.set_page_config(page_title="Dashboard Financeiro Pro", layout="wide", page_icon="🚀")

# --- 2. CONFIGURAÇÕES GERAIS ---
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1eyzBHcfvHhVBDPn3pN4RKzgfaW74tMiDYvP3z0-7jrU/edit?usp=sharing"

# --- 3. SISTEMA DE LOGIN (NOVIDADE) ---
def check_password():
    """Retorna `True` se o usuário tiver a senha correta."""
    
    def password_entered():
        """Verifica se a senha inserida bate com a senha dos segredos."""
        if st.session_state["password"] == st.secrets["senha_acesso"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Remove a senha da memória por segurança
        else:
            st.session_state["password_correct"] = False

    # Se a senha já estiver correta na sessão, retorna True
    if st.session_state.get("password_correct", False):
        return True

    # Mostra o campo de entrada de senha
    st.subheader("🔒 Acesso Restrito")
    st.text_input(
        "Digite a senha para acessar o painel:", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    if "password_correct" in st.session_state:
        st.error("😕 Senha incorreta. Tente novamente.")
        
    return False

# Bloqueia a execução se a senha não estiver correta
if not check_password():
    st.stop()

# --- DAQUI PARA BAIXO: SEU CÓDIGO ORIGINAL (MANTIDO) ---

# --- FUNÇÃO DE PROCESSAMENTO DE PARCELAS ---
def processar_parcelas(df_original):
    novas_linhas = []
    compras_parceladas = df_original[df_original['Parcelas'] > 1]
    compras_a_vista = df_original[df_original['Parcelas'] <= 1].copy()
    
    for index, row in compras_parceladas.iterrows():
        valor_total = row['Valor']
        qtd_parcelas = int(row['Parcelas'])
        valor_parcela = valor_total / qtd_parcelas
        data_inicial = row['Data']
        
        for i in range(qtd_parcelas):
            nova_linha = row.copy()
            nova_linha['Data'] = data_inicial + relativedelta(months=i)
            nova_linha['Valor'] = valor_parcela
            nova_linha['Descrição'] = f"{row['Descrição']} ({i+1}/{qtd_parcelas})"
            novas_linhas.append(nova_linha)
            
    if novas_linhas:
        df_parcelado = pd.DataFrame(novas_linhas)
        df_final = pd.concat([compras_a_vista, df_parcelado], ignore_index=True)
    else:
        df_final = compras_a_vista
    return df_final.sort_values(by="Data")

# --- CARREGAMENTO DE DADOS ---
st.title("🚀 Controle Financeiro & Investimentos")

conn = st.connection("gsheets", type=GSheetsConnection)

try:
    data = conn.read(
        spreadsheet=PLANILHA_URL,
        usecols=list(range(8)),
        ttl=0
    )
    df_raw = pd.DataFrame(data)
except Exception as e:
    st.error("Erro ao conectar na planilha. Verifique o link e as permissões.")
    st.stop()

# --- TRATAMENTO DE DADOS ---
df_raw['Data'] = pd.to_datetime(df_raw['Data'], format="%d/%m/%Y", dayfirst=True, errors='coerce')

# Limpeza da coluna Valor
df_raw['Valor'] = df_raw['Valor'].astype(str).str.replace('R$', '', regex=False).str.strip()
df_raw['Valor'] = df_raw['Valor'].str.replace('.', '', regex=False)
df_raw['Valor'] = df_raw['Valor'].str.replace(',', '.', regex=False)
df_raw['Valor'] = pd.to_numeric(df_raw['Valor'], errors='coerce').fillna(0)

# Coluna Parcelas
df_raw['Parcelas'] = pd.to_numeric(df_raw['Parcelas'], errors='coerce').fillna(1).astype(int)

# Aplicando a Mágica das Parcelas
df = processar_parcelas(df_raw)

# Criando colunas auxiliares de Data
df['Mes_Ano'] = df['Data'].dt.to_period('M')

# --- BARRA LATERAL (CONFIGURAÇÕES E FILTROS) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    st.subheader("Simulador de Investimentos")
    taxa_cdi = st.number_input("Taxa CDI Anual (%)", value=11.25)
    percentual_cdi = st.number_input("% do CDI do seu fundo", value=120)
    
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    st.subheader("Filtros de Visualização")
    
    if not df.empty:
        min_date = df['Data'].min().date()
        max_date = df['Data'].max().date()
        data_selecao = st.date_input("Período de Análise", [min_date, max_date])
    else:
        st.warning("Sem dados para filtrar.")

# Aplicando filtro de data
try:
    if not df.empty and len(data_selecao) == 2:
        mask = (df['Data'].dt.date >= data_selecao[0]) & (df['Data'].dt.date <= data_selecao[1])
        df_filtered = df.loc[mask]
    else:
        df_filtered = df
except:
    df_filtered = df

# --- CÁLCULOS ESTRUTURAIS ---
if not df.empty:
    # 1. Separar Investimento
    df['Is_Investimento'] = df['Categoria'].str.contains('Investimento', case=False, na=False)

    # 2. Agrupamento Mensal
    receitas_mensal = df[df['Tipo'] == 'Receita'].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()
    despesas_mensal = df[df['Tipo'] == 'Despesa'].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()
    invest_mensal = df[(df['Tipo'] == 'Despesa') & (df['Is_Investimento'])].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()

    df_evolucao = pd.DataFrame({
        'Receitas': receitas_mensal,
        'Despesas_Totais': despesas_mensal,
        'Aportes': invest_mensal
    }).fillna(0)

    # Saldos
    df_evolucao['Saldo_Mes'] = df_evolucao['Receitas'] - df_evolucao['Despesas_Totais']
    df_evolucao['Saldo_Acumulado_Conta'] = df_evolucao['Saldo_Mes'].cumsum()

    # --- SIMULAÇÃO DE RENDIMENTO ---
    taxa_mensal = ((1 + (taxa_cdi/100))**(1/12) - 1) * (percentual_cdi/100)
    
    saldo_invest = 0
    lista_invest_simulado = []
    
    # Garante que a ordem temporal está correta
    df_evolucao = df_evolucao.sort_index()
    
    for aporte in df_evolucao['Aportes']:
        saldo_invest = saldo_invest * (1 + taxa_mensal)
        saldo_invest += aporte
        lista_invest_simulado.append(saldo_invest)

    df_evolucao['Investimento_Com_Rendimento'] = lista_invest_simulado

    # --- SEÇÃO 1: CABEÇALHO E ALERTAS ---
    if not df_evolucao.empty:
        ultimo_mes = df_evolucao.index[-1]
        saldo_atual_conta = df_evolucao.loc[ultimo_mes, 'Saldo_Acumulado_Conta']
        saldo_total_investido = df_evolucao.loc[ultimo_mes, 'Investimento_Com_Rendimento']

        # Lógica de Alerta de Saúde Financeira
        total_receitas_geral = df_evolucao['Receitas'].sum()
        savings_ratio = (df_evolucao['Aportes'].sum() / total_receitas_geral) * 100 if total_receitas_geral > 0 else 0

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Saldo em Conta (Acumulado)", f"R$ {saldo_atual_conta:,.2f}", 
                  delta="Crítico" if saldo_atual_conta < 0 else "Positivo", 
                  delta_color="normal" if saldo_atual_conta >= 0 else "inverse")

        c2.metric("Total Investido (Est.)", f"R$ {saldo_total_investido:,.2f}", f"+{(taxa_mensal*100):.2f}% a.m.")

        if saldo_atual_conta < 0:
            st.error(f"🚨 ATENÇÃO: Sua conta está no vermelho em R$ {saldo_atual_conta:,.2f}. Pare de gastar imediatamente ou resgate investimentos.")
        else:
            st.success(f"✅ Fluxo de Caixa Saudável. Você está acumulando capital.")

        # Score de Saúde
        score = min(100, int((savings_ratio / 20) * 100))
        c3.metric("Financial Score", f"{score}/100", help="Baseado na meta de investir 20% da renda.")
        c4.metric("Taxa de Poupança Real", f"{savings_ratio:.1f}%")

    st.divider()

    # --- SEÇÃO 2: GRÁFICOS ---
    c1, c2 = st.columns([2, 1])

    # Prepara dados para o gráfico
    df_evolucao.index = df_evolucao.index.astype(str) # Converte index para string para o Plotly
    
    with c1:
        st.subheader("📊 Evolução Mensal")
        
        df_chart = df_evolucao.reset_index().melt(
            id_vars=['Data'],  # O nome do índice virou 'Data' no reset_index
            value_vars=['Receitas', 'Despesas_Totais'],
            var_name='Tipo', 
            value_name='Valor'
        ).rename(columns={'Data': 'Mes_Ano'})

        fig = px.bar(
            df_chart, 
            x='Mes_Ano', 
            y='Valor', 
            color='Tipo',
            barmode='group',
            text_auto='.2s',
            color_discrete_map={'Receitas': '#2ecc71', 'Despesas_Totais': '#e74c3c'}
        )
        
        # Adiciona Linha de Saldo Acumulado
        fig.add_scatter(
            x=df_evolucao.index, 
            y=df_evolucao['Saldo_Acumulado_Conta'], 
            mode='lines+markers', 
            name='Saldo Acumulado',
            line=dict(color='blue', width=3)
        )
        
        fig.update_layout(xaxis_title="Mês", yaxis_title="Valor (R$)", xaxis_type='category')
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("📌 Resumo do Mês")
        
        ultimo_mes_dados = df_evolucao.iloc[-1]
        nome_mes_dados = df_evolucao.index[-1]
        
        st.markdown(f"**Referência:** {nome_mes_dados}")
        st.metric("Receita", f"R$ {ultimo_mes_dados['Receitas']:,.2f}", "Entradas")
        st.metric("Despesas", f"R$ {ultimo_mes_dados['Despesas_Totais']:,.2f}", "- Saídas", delta_color="inverse")
        st.metric("Saldo do Mês", f"R$ {ultimo_mes_dados['Saldo_Mes']:,.2f}", 
                  "Positivo" if ultimo_mes_dados['Saldo_Mes'] > 0 else "Negativo")

    # --- SEÇÃO 3: DETALHAMENTO ---
    st.divider()
    c_filtro, c_tabela = st.columns([1, 2])

    with c_filtro:
        st.subheader("🔍 Raio-X Mensal")
        
        meses_disp = df_evolucao.index.tolist()
        mes_foco = st.selectbox("Escolha um mês:", meses_disp[::-1])
        
        # Filtro corrigido usando Mes_Ano criado lá no começo
        df_detalhe = df[df['Mes_Ano'].astype(str) == mes_foco]
        
        # Gráfico de Pizza
        df_pizza = df_detalhe[df_detalhe['Tipo'] == 'Despesa']
        if not df_pizza.empty:
            df_categoria = df_pizza.groupby('Categoria')['Valor'].sum().reset_index()
            fig_pizza = px.pie(df_categoria, values='Valor', names='Categoria', hole=0.5, 
                               color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pizza.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=250)
            fig_pizza.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pizza, use_container_width=True)
        else:
            st.info("Sem despesas neste mês.")

    with c_tabela:
        st.subheader(f"📝 Extrato: {mes_foco}")
        st.dataframe(
            df_detalhe[['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo', 'Parcelas']].sort_values('Data'),
            hide_index=True,
            use_container_width=True,
            height=500
        )
else:
    st.info("Aguardando dados... Preencha sua planilha!")

