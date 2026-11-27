"""
Carrega os resumos agregados do ERP e prepara os dados do painel.

Variáveis de ambiente:
  ERP_URL       endereço do ERP (padrão: https://vitta-erp.onrender.com)
  EXPORT_TOKEN  o mesmo token configurado no ERP
"""
import io
import os

import pandas as pd
import requests

ERP_URL = os.environ.get("ERP_URL", "https://vitta-erp.onrender.com").rstrip("/")
EXPORT_TOKEN = os.environ.get("EXPORT_TOKEN", "")

RESUMOS = ["mensal", "especialidade", "canal", "convenio"]


def baixar(caminho):
    if not EXPORT_TOKEN:
        raise RuntimeError("A variável EXPORT_TOKEN não está definida neste serviço.")
    resposta = requests.get(f"{ERP_URL}/exportar/{caminho}",
                            headers={"X-Token": EXPORT_TOKEN}, timeout=180)
    resposta.raise_for_status()
    return pd.read_csv(io.StringIO(resposta.text), sep=";")


def preparar():
    """Baixa os resumos mensais do ERP. Cada um é pequeno, então o consumo de memória é baixo."""
    dados = {}
    for nome in RESUMOS:
        df = baixar(f"resumo/{nome}.csv")
        df["mes"] = pd.to_datetime(df["mes"] + "-01")
        dados[nome] = df
    return dados


def filtrar(dados, ini, fim, unidades):
    """Filtra por meses inteiros e pelas unidades escolhidas."""
    inicio = pd.Timestamp(ini.replace(day=1))
    final = pd.Timestamp(fim)
    filtrado = {}
    for nome, df in dados.items():
        mascara = (df["mes"] >= inicio) & (df["mes"] <= final) & (df["unidade"].isin(unidades))
        filtrado[nome] = df[mascara]
    return filtrado


def indicadores(f):
    m = f["mensal"]
    realizadas = int(m["realizados"].sum())
    nao_compareceu = int(m["nao_compareceu"].sum())
    canceladas = int(m["cancelados"].sum())
    total = int(m["agendados"].sum())
    encerradas = realizadas + nao_compareceu
    bruto = float(m["bruto"].sum())
    glosa = float(m["glosa"].sum())
    liquido = float(m["liquido"].sum())
    recebido = float(m["recebido"].sum())
    return {
        "realizadas": realizadas,
        "total": total,
        "nao_compareceu": nao_compareceu,
        "canceladas": canceladas,
        "taxa_nao_comparecimento": nao_compareceu / encerradas if encerradas else 0.0,
        "taxa_cancelamento": canceladas / total if total else 0.0,
        "bruto": bruto,
        "glosa": glosa,
        "taxa_glosa": glosa / bruto if bruto else 0.0,
        "liquido": liquido,
        "recebido": recebido,
        "a_receber": liquido - recebido,
        "ticket_medio": bruto / realizadas if realizadas else 0.0,
    }


def serie_mensal(f):
    return (f["mensal"].groupby("mes", as_index=False)["realizados"].sum()
            .rename(columns={"realizados": "consultas"}))


def faturamento_mensal(f):
    return f["mensal"].groupby("mes", as_index=False)["liquido"].sum()


def taxa_por_especialidade(f):
    e = f["especialidade"].groupby("especialidade", as_index=False)[["realizados", "nao_compareceu"]].sum()
    encerradas = (e["realizados"] + e["nao_compareceu"]).where(lambda s: s > 0)
    e["taxa"] = e["nao_compareceu"] / encerradas
    return e.dropna(subset=["taxa"]).sort_values("taxa", ascending=False)[["especialidade", "taxa"]]


def canais(f):
    return f["canal"].groupby("canal", as_index=False)["agendados"].sum()


def por_convenio(f):
    c = f["convenio"].groupby("convenio", as_index=False)[["bruto", "glosa", "liquido"]].sum()
    c["taxa_glosa"] = c["glosa"] / c["bruto"].where(lambda s: s > 0)
    return c.sort_values("taxa_glosa", ascending=False)


def resultado_unidades(f):
    """Receita, custos e ponto de equilíbrio por unidade, no período filtrado."""
    m = f["mensal"].groupby("unidade", as_index=False)[["liquido", "fixo", "variavel"]].sum()
    m = m.rename(columns={"liquido": "receita"})
    m["resultado"] = m["receita"] - m["fixo"] - m["variavel"]
    margem = 1 - m["variavel"] / m["receita"].where(m["receita"] > 0)
    m["margem_contribuicao"] = margem.where(margem > 0)
    m["ponto_equilibrio"] = m["fixo"] / m["margem_contribuicao"]
    m["folga"] = m["receita"] - m["ponto_equilibrio"]
    return m
