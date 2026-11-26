"""
Carrega as tabelas do ERP pela rota /exportar e prepara os dados do painel.

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

TABELAS = ["agendamentos", "atendimentos", "faturamento", "despesas", "unidades",
           "medicos", "especialidades", "procedimentos", "convenios"]


def baixar(tabela):
    if not EXPORT_TOKEN:
        raise RuntimeError("A variável EXPORT_TOKEN não está definida neste serviço.")
    resposta = requests.get(f"{ERP_URL}/exportar/{tabela}.csv",
                            headers={"X-Token": EXPORT_TOKEN}, timeout=180)
    resposta.raise_for_status()
    return pd.read_csv(io.StringIO(resposta.text), sep=";")


def preparar():
    """Baixa as tabelas e devolve os DataFrames já unidos, prontos para o painel."""
    t = {nome: baixar(nome) for nome in TABELAS}

    unidades = t["unidades"][["id_unidade", "nome"]].rename(columns={"nome": "unidade"})
    especialidades = t["especialidades"].rename(columns={"nome": "especialidade"})

    ag = t["agendamentos"].copy()
    ag["data"] = pd.to_datetime(ag["data_hora_agendada"])
    ag = ag.merge(unidades, on="id_unidade", how="left")
    ag = ag.merge(t["medicos"][["id_medico", "id_especialidade"]], on="id_medico", how="left")
    ag = ag.merge(especialidades[["id_especialidade", "especialidade"]],
                  on="id_especialidade", how="left")

    at = t["atendimentos"][["id_atendimento", "id_agendamento"]]
    fat = t["faturamento"].copy()
    fat["data_emissao"] = pd.to_datetime(fat["data_emissao"])
    fat["data_recebimento"] = pd.to_datetime(fat["data_recebimento"])
    fat = fat.merge(at, on="id_atendimento", how="left")
    fat = fat.merge(ag[["id_agendamento", "id_unidade", "unidade", "especialidade"]],
                    on="id_agendamento", how="left")
    fat = fat.merge(t["convenios"][["id_convenio", "nome"]].rename(columns={"nome": "convenio"}),
                    on="id_convenio", how="left")

    desp = t["despesas"].copy()
    desp["competencia"] = pd.to_datetime(desp["competencia"])
    desp = desp.merge(unidades, on="id_unidade", how="left")

    return {"ag": ag, "fat": fat, "desp": desp}


def filtrar(dados, ini, fim, unidades):
    """Aplica o período e as unidades escolhidas em todas as tabelas."""
    ag = dados["ag"]
    fat = dados["fat"]
    desp = dados["desp"]

    ag = ag[(ag["data"].dt.date >= ini) & (ag["data"].dt.date <= fim)]
    fat = fat[(fat["data_emissao"].dt.date >= ini) & (fat["data_emissao"].dt.date <= fim)]
    desp = desp[(desp["competencia"].dt.date >= ini.replace(day=1))
                & (desp["competencia"].dt.date <= fim)]

    ag = ag[ag["unidade"].isin(unidades)]
    fat = fat[fat["unidade"].isin(unidades)]
    desp = desp[desp["unidade"].isin(unidades)]
    return ag, fat, desp


def indicadores(ag, fat):
    realizadas = int((ag["status"] == "Realizado").sum())
    nao_compareceu = int((ag["status"] == "Não compareceu").sum())
    canceladas = int((ag["status"] == "Cancelado").sum())
    encerradas = realizadas + nao_compareceu
    total = len(ag)
    bruto = float(fat["valor_bruto"].sum())
    glosa = float(fat["valor_glosa"].sum())
    liquido = float(fat["valor_liquido"].sum())
    recebido = float(fat.loc[fat["data_recebimento"].notna(), "valor_liquido"].sum())
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


def serie_mensal(ag):
    ag = ag.assign(mes=ag["data"].dt.to_period("M").dt.to_timestamp())
    return (ag[ag["status"] == "Realizado"].groupby("mes").size()
            .rename("consultas").reset_index())


def faturamento_mensal(fat):
    fat = fat.assign(mes=fat["data_emissao"].dt.to_period("M").dt.to_timestamp())
    return fat.groupby("mes")["valor_liquido"].sum().rename("liquido").reset_index()


def taxa_nao_comparecimento_por_especialidade(ag):
    encerrados = ag[ag["status"].isin(["Realizado", "Não compareceu"])].copy()
    encerrados["falta"] = encerrados["status"].eq("Não compareceu")
    return (encerrados.groupby("especialidade")["falta"].mean()
            .sort_values(ascending=False).rename("taxa").reset_index())


def canais(ag):
    return ag.groupby("canal").size().rename("agendamentos").reset_index()


def resultado_unidades(fat, desp):
    """Receita, custos e ponto de equilíbrio por unidade, no período filtrado."""
    receita = fat.groupby("unidade")["valor_liquido"].sum().rename("receita")
    custos = (desp.pivot_table(index="unidade", columns="tipo", values="valor",
                               aggfunc="sum")
              .reindex(columns=["Fixo", "Variável"], fill_value=0))
    df = pd.DataFrame(receita).join(custos, how="outer").fillna(0)
    df.columns = ["receita", "fixo", "variavel"]
    df["resultado"] = df["receita"] - df["fixo"] - df["variavel"]
    margem = 1 - df["variavel"] / df["receita"].where(df["receita"] > 0)
    df["margem_contribuicao"] = margem
    df["ponto_equilibrio"] = df["fixo"] / margem
    df["folga"] = df["receita"] - df["ponto_equilibrio"]
    return df.reset_index()
