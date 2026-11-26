"""
Painel de gestão da Vitta Clínicas, em Streamlit.
Lê os dados do ERP pela rota de exportação, com filtros interativos.

Rodar localmente:  streamlit run dashboard.py
"""
import pandas as pd
import plotly.express as px
import streamlit as st

import dados


def reais(valor):
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def percentual(valor):
    return f"{valor * 100:.1f}%".replace(".", ",")


st.set_page_config(page_title="Vitta Clínicas · Painel", layout="wide")
st.title("Vitta Clínicas · Painel de gestão")
st.caption("Dados do ERP. Tudo fictício, para fins de estudo.")


@st.cache_data(ttl=900, show_spinner="Carregando dados do ERP. A primeira vez pode levar alguns minutos...")
def carregar():
    return dados.preparar()


try:
    base = carregar()
except Exception as erro:
    st.error(f"Não foi possível carregar os dados do ERP: {erro}")
    st.info("Confira se o serviço do ERP está Live e se EXPORT_TOKEN é o mesmo nos dois serviços.")
    st.stop()

todas_unidades = sorted(base["ag"]["unidade"].dropna().unique())
data_min = base["ag"]["data"].min().date()
data_max = base["ag"]["data"].max().date()

with st.sidebar:
    st.header("Filtros")
    periodo = st.date_input("Período", value=(data_min, data_max),
                            min_value=data_min, max_value=data_max)
    escolhidas = st.multiselect("Unidades", todas_unidades, default=todas_unidades)
    if st.button("Atualizar dados do ERP"):
        st.cache_data.clear()
        st.rerun()

if len(periodo) != 2:
    st.info("Selecione a data inicial e a data final no filtro.")
    st.stop()
if not escolhidas:
    st.warning("Selecione ao menos uma unidade.")
    st.stop()

ini, fim = periodo
ag, fat, desp = dados.filtrar(base, ini, fim, escolhidas)
k = dados.indicadores(ag, fat)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Consultas realizadas", f"{k['realizadas']:,}".replace(",", "."))
c2.metric("Não comparecimento", percentual(k["taxa_nao_comparecimento"]))
c3.metric("Cancelamentos", percentual(k["taxa_cancelamento"]))
c4.metric("Faturamento líquido", reais(k["liquido"]))
c5.metric("Ticket médio", reais(k["ticket_medio"]))
c6.metric("Taxa de glosa", percentual(k["taxa_glosa"]))

aba_op, aba_fin, aba_uni = st.tabs(["Operação", "Financeiro", "Unidades e resultado"])

with aba_op:
    st.plotly_chart(px.line(dados.serie_mensal(ag), x="mes", y="consultas", markers=True,
                            title="Consultas realizadas por mês"))
    col1, col2 = st.columns(2)
    with col1:
        taxa = dados.taxa_nao_comparecimento_por_especialidade(ag)
        fig = px.bar(taxa, x="taxa", y="especialidade", orientation="h",
                     title="Não comparecimento por especialidade")
        fig.update_xaxes(tickformat=".0%")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig)
    with col2:
        st.plotly_chart(px.bar(dados.canais(ag), x="canal", y="agendamentos",
                               title="Agendamentos por canal"))

with aba_fin:
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(px.bar(dados.faturamento_mensal(fat), x="mes", y="liquido",
                               title="Faturamento líquido por mês (data de emissão)"))
    with col2:
        situacao = pd.DataFrame({"situação": ["Recebido", "A receber"],
                                 "valor": [k["recebido"], k["a_receber"]]})
        st.plotly_chart(px.pie(situacao, names="situação", values="valor",
                               title="Recebido x a receber"))

    st.subheader("Convênios e glosas")
    por_convenio = (fat.groupby("convenio")
                    .agg(bruto=("valor_bruto", "sum"),
                         glosa=("valor_glosa", "sum"),
                         liquido=("valor_liquido", "sum"))
                    .reset_index())
    por_convenio["taxa_glosa"] = por_convenio["glosa"] / por_convenio["bruto"]
    st.dataframe(por_convenio.sort_values("taxa_glosa", ascending=False).round(2),
                 hide_index=True)

with aba_uni:
    if fat.empty or desp.empty:
        st.info("Não há dados de faturamento ou despesas no período e nas unidades escolhidas.")
    else:
        res = dados.resultado_unidades(fat, desp)
        st.metric("Unidades acima do ponto de equilíbrio",
                  f"{int((res['folga'] > 0).sum())} de {len(res)}")
        st.plotly_chart(px.bar(res.sort_values("resultado"), x="resultado", y="unidade",
                               orientation="h", title="Resultado do período por unidade (R$)"))
        tabela = res.copy()
        for coluna in ["receita", "fixo", "variavel", "resultado", "ponto_equilibrio", "folga"]:
            tabela[coluna] = tabela[coluna].round(0)
        st.dataframe(tabela.sort_values("folga", ascending=False), hide_index=True)
        st.caption("Os custos são estimativas do gerador de dados: aluguel e folha proporcionais "
                   "às salas, e honorários de 32%, insumos de 6% e impostos de 4% da receita. "
                   "O ponto de equilíbrio usa os custos fixos e a margem de contribuição do período.")
