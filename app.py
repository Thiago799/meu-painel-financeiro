import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
import numpy as np

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard Financeiro Pro", layout="wide", page_icon="🚀")

# --- FUNÇÃO DE PROCESSAMENTO DE PARCELAS (Lógica Anterior) ---
def processar_parcelas(df_original):
    novas_linhas = []
    # Filtra onde tem 'x' ou '/' na coluna Parcelas ou é maior que 1
    # Assumindo que a coluna já vem tratada como número, se for > 1 processa
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

# Cache de 10 segundos para ser quase real-time
# Na linha 45:
data = conn.read(
    spreadsheet="https://docs.google.com/spreadsheets/d/1eyzBHcfvHhVBDPn3pN4RKzgfaW74tMiDYvP3z0-7jrU/edit?usp=sharing",
    usecols=list(range(8)),
    ttl=10)
df_raw = pd.DataFrame(data)

# Tratamento Inicial
# --- Tratamento Inicial ---
# Converte a data
df_raw['Data'] = pd.to_datetime(df_raw['Data'], format="%d/%m/%Y", dayfirst=True)

# Limpeza da coluna Valor (Corrige o problema do R$ 0,00)
# 1. Transforma em texto
# 2. Remove o "R$" e espaços
# 3. Remove pontos de milhar (ex: 1.000 -> 1000)
# 4. Troca vírgula decimal por ponto (ex: 50,20 -> 50.20)
df_raw['Valor'] = df_raw['Valor'].astype(str).str.replace('R$', '', regex=False).str.strip()
df_raw['Valor'] = df_raw['Valor'].str.replace('.', '', regex=False)
df_raw['Valor'] = df_raw['Valor'].str.replace(',', '.', regex=False)

# Agora converte para número
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
    
    st.divider()
    st.subheader("Filtros de Visualização")
    # Filtro de Data Global
    min_date = df['Data'].min().date()
    max_date = df['Data'].max().date()
    data_selecao = st.date_input("Período de Análise", [min_date, max_date])

# Aplicando filtro de data no DataFrame principal (apenas para visualização de tabelas e detalhes)
try:
    mask = (df['Data'].dt.date >= data_selecao[0]) & (df['Data'].dt.date <= data_selecao[1])
    df_filtered = df.loc[mask]
except:
    df_filtered = df # Fallback caso o usuário não selecione range completo

# --- CÁLCULOS ESTRUTURAIS (O CORAÇÃO DO SISTEMA) ---

# 1. Separar o que é Investimento do que é Gasto Real
# Assumimos que a categoria se chama 'Investimento' ou 'Investimentos'
df['Is_Investimento'] = df['Categoria'].str.contains('Investimento', case=False, na=False)

# 2. Agrupamento Mensal para Evolução
# Agrupamos por mês para fazer o cálculo de saldo acumulado
df_mensal = df.groupby(df['Data'].dt.to_period('M')).agg({
    'Valor': lambda x: sum([v if t == 'Receita' else -v for v, t in zip(x, df.loc[x.index, 'Tipo'])])
}).rename(columns={'Valor': 'Resultado_Mensal'})

# Calculando receitas e despesas separadas por mês
receitas_mensal = df[df['Tipo'] == 'Receita'].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()
# Despesas totais (incluindo aportes de investimento, pois saiu da conta)
despesas_mensal = df[df['Tipo'] == 'Despesa'].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()
# Aportes em Investimento
invest_mensal = df[(df['Tipo'] == 'Despesa') & (df['Is_Investimento'])].groupby(df['Data'].dt.to_period('M'))['Valor'].sum()

# Consolidando Tabela Mestra Mensal
df_evolucao = pd.DataFrame({
    'Receitas': receitas_mensal,
    'Despesas_Totais': despesas_mensal,
    'Aportes': invest_mensal
}).fillna(0)

# O Saldo da CONTA CORRENTE (Receita - Despesas Totais)
df_evolucao['Saldo_Mes'] = df_evolucao['Receitas'] - df_evolucao['Despesas_Totais']

# O Saldo ACUMULADO (Acarreta o negativo/positivo do mês anterior)
df_evolucao['Saldo_Acumulado_Conta'] = df_evolucao['Saldo_Mes'].cumsum()

# O Saldo de INVESTIMENTOS (Acumulado dos aportes)
# Nota: Aqui entra o cálculo básico do acumulado.
df_evolucao['Investimento_Acumulado'] = df_evolucao['Aportes'].cumsum()

# --- SIMULAÇÃO DE RENDIMENTO (Cálculo Composto Simplificado) ---
# Transformando taxa anual em mensal
taxa_mensal = ((1 + (taxa_cdi/100))**(1/12) - 1) * (percentual_cdi/100)
df_evolucao['Investimento_Com_Rendimento'] = 0.0

saldo_invest = 0
lista_invest_simulado = []
for aporte in df_evolucao['Aportes']:
    # Aplica rendimento no saldo anterior
    saldo_invest = saldo_invest * (1 + taxa_mensal)
    # Soma o novo aporte
    saldo_invest += aporte
    lista_invest_simulado.append(saldo_invest)

df_evolucao['Investimento_Com_Rendimento'] = lista_invest_simulado

# --- DASHBOARD LAYOUT ---

# --- SEÇÃO 1: CABEÇALHO E ALERTAS ---
ultimo_mes = df_evolucao.index[-1]
saldo_atual_conta = df_evolucao.loc[ultimo_mes, 'Saldo_Acumulado_Conta']
saldo_total_investido = df_evolucao.loc[ultimo_mes, 'Investimento_Com_Rendimento']

# Lógica de Alerta de Saúde Financeira
savings_ratio = (df_evolucao['Aportes'].sum() / df_evolucao['Receitas'].sum()) * 100 if df_evolucao['Receitas'].sum() > 0 else 0

c1, c2, c3, c4 = st.columns(4)

c1.metric("Saldo em Conta (Acumulado)", f"R$ {saldo_atual_conta:,.2f}", 
          delta="Crítico" if saldo_atual_conta < 0 else "Positivo", 
          delta_color="normal" if saldo_atual_conta >= 0 else "inverse")

c2.metric("Total Investido (Est.)", f"R$ {saldo_total_investido:,.2f}", f"+{(taxa_mensal*100):.2f}% a.m.")

if saldo_atual_conta < 0:
    st.error(f"🚨 ATENÇÃO: Sua conta está no vermelho em R$ {saldo_atual_conta:,.2f}. Pare de gastar imediatamente ou resgate investimentos.")
else:
    st.success(f"✅ Fluxo de Caixa Saudável. Você está acumulando capital.")

# Score de Saúde (0 a 100) - Baseado em poupar 20% da renda
score = min(100, int((savings_ratio / 20) * 100))
c3.metric("Financial Score", f"{score}/100", help="Baseado na meta de investir 20% da renda.")
c4.metric("Taxa de Poupança Real", f"{savings_ratio:.1f}%")

st.divider()

# --- SEÇÃO 2: GRÁFICOS E CÁLCULOS MENSAIS ---

st.divider()
c1, c2 = st.columns([2, 1])

# 1. Preparação dos Dados
# Formatamos como "2025-02" para garantir a ordem correta
df['Mes_Ano'] = df['Data'].dt.to_period('M').astype(str)

# Cria a tabela de evolução
df_evolucao = df.groupby('Mes_Ano').apply(
    lambda x: pd.Series({
        'Receitas': x.loc[x['Tipo'] == 'Receita', 'Valor'].sum(),
        'Despesas_Totais': x.loc[x['Tipo'] == 'Despesa', 'Valor'].sum()
    })
)
df_evolucao['Saldo_Mes'] = df_evolucao['Receitas'] - df_evolucao['Despesas_Totais']
df_evolucao['Saldo_Acumulado'] = df_evolucao['Saldo_Mes'].cumsum()

# 2. O Gráfico
with c1:
    st.subheader("📊 Evolução Mensal")
    
    # Prepara dados para o gráfico
    df_chart = df_evolucao.reset_index().melt(
        id_vars=['Mes_Ano'], 
        value_vars=['Receitas', 'Despesas_Totais'],
        var_name='Tipo', 
        value_name='Valor'
    )

    # Gráfico de Barras
    fig = px.bar(
        df_chart, 
        x='Mes_Ano', 
        y='Valor', 
        color='Tipo',
        barmode='group', # Garante barras lado a lado
        text_auto='.2s',
        color_discrete_map={'Receitas': '#2ecc71', 'Despesas_Totais': '#e74c3c'}
    )
    
    # Linha de Saldo
    fig.add_scatter(
        x=df_evolucao.index, 
        y=df_evolucao['Saldo_Acumulado'], 
        mode='lines+markers', 
        name='Saldo Acumulado',
        line=dict(color='blue', width=3)
    )
    
    # --- AQUI ESTÁ A CORREÇÃO ---
    # "xaxis_type='category'" força o gráfico a mostrar apenas os nomes dos meses
    # e não uma linha do tempo com dias/semanas.
    fig.update_layout(
        xaxis_title="Mês", 
        yaxis_title="Valor (R$)",
        xaxis_type='category' 
    )
    
    st.plotly_chart(fig, use_container_width=True)

with c2:
        st.subheader("📌 Resumo do Mês")
        
        # Pega os dados do último mês disponível (o mais recente)
        ultimo_mes = df_evolucao.iloc[-1]
        nome_mes = df_evolucao.index[-1] # Ex: 2025-02
        
        st.markdown(f"**Referência:** {nome_mes}")
        
        st.metric(
            label="Receita", 
            value=f"R$ {ultimo_mes['Receitas']:,.2f}",
            delta="Entradas"
        )
        
        st.metric(
            label="Despesas", 
            value=f"R$ {ultimo_mes['Despesas_Totais']:,.2f}",
            delta="- Saídas",
            delta_color="inverse" # Fica vermelho se aumentar
        )
        
        saldo = ultimo_mes['Saldo_Mes']
        st.metric(
            label="Saldo do Mês", 
            value=f"R$ {saldo:,.2f}",
            delta="Livre para Investir" if saldo > 0 else "No Vermelho",
            delta_color="normal"
        )

# --- SEÇÃO 3: DETALHAMENTO (DRILL DOWN) ---

st.divider()

# Layout: Coluna Esquerda (Filtros e Gráfico) | Coluna Direita (Tabela)
c_filtro, c_tabela = st.columns([1, 2])

with c_filtro:
    st.subheader("🔍 Raio-X Mensal")
    
    # 1. Seletor de Mês
    meses_disp = df_evolucao.index.astype(str).tolist()
    mes_foco = st.selectbox("Escolha um mês:", meses_disp[::-1])
    
    # 2. Filtra os dados GERAIS para o mês escolhido (Prepara os dados)
    # Importante: Fazemos isso aqui para usar tanto no gráfico quanto na tabela
    df_detalhe = df[df['Mes_Ano'].astype(str) == mes_foco]
    
    # 3. Métricas Rápidas
    total_receitas = df_detalhe.loc[df_detalhe['Tipo'] == 'Receita', 'Valor'].sum()
    total_despesas = df_detalhe.loc[df_detalhe['Tipo'] == 'Despesa', 'Valor'].sum()
    saldo_foco = total_receitas - total_despesas
    
    st.metric("Resultado do Mês", f"R$ {saldo_foco:,.2f}", delta=f"{'Lucro' if saldo_foco > 0 else 'Prejuízo'}")

    # 4. GRÁFICO DE ROSCA (NOVIDADE AQUI!)
    st.markdown("---")
    st.caption("Distribuição de Gastos")
    
    # Filtra só despesas para o gráfico
    df_pizza = df_detalhe[df_detalhe['Tipo'] == 'Despesa']
    
    if not df_pizza.empty:
        # Agrupa por Categoria
        df_categoria = df_pizza.groupby('Categoria')['Valor'].sum().reset_index()
        
        fig_pizza = px.pie(
            df_categoria, 
            values='Valor', 
            names='Categoria',
            hole=0.5, # Faz o buraco no meio (Rosca)
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        
        # Ajustes visuais para caber na coluna estreita
        fig_pizza.update_layout(
            showlegend=False, 
            margin=dict(t=0, b=0, l=0, r=0),
            height=250
        )
        # Mostra o nome da categoria ao passar o mouse ou no gráfico
        fig_pizza.update_traces(textposition='inside', textinfo='percent+label')
        
        st.plotly_chart(fig_pizza, use_container_width=True)
    else:
        st.info("Sem despesas neste mês.")

with c_tabela:
    st.subheader(f"📝 Extrato: {mes_foco}")
    
    # Mostra a tabela (usando o df_detalhe que já filtramos lá no começo)
    st.dataframe(
        df_detalhe[['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo', 'Parcelas']].sort_values('Data'),
        hide_index=True,
        use_container_width=True,
        height=500 # Altura fixa para ficar elegante
    )