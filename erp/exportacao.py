"""
Exportação de dados do ERP para o Power BI e para o painel.

Autenticação: cabeçalho X-Token com o valor da variável EXPORT_TOKEN.

Rotas:
  GET /exportar/<tabela>.csv         tabela completa (uso no Power BI Desktop)
  GET /exportar/resumo/<nome>.csv    resumo agregado por mês e unidade (uso no painel)
"""
import csv
import hmac
import io
import os

from flask import Response, abort, request

from app import app, db

TOKEN = os.environ.get("EXPORT_TOKEN", "")

TABELAS = {
    "agendamentos", "atendimentos", "faturamento", "despesas",
    "unidades", "medicos", "especialidades", "procedimentos",
    "convenios", "pacientes",
}


def _autorizar():
    if not TOKEN:
        abort(503)  # exportação desligada enquanto EXPORT_TOKEN não estiver definido
    enviado = request.headers.get("X-Token", "")
    if not hmac.compare_digest(enviado.encode(), TOKEN.encode()):
        abort(401)


def _resposta_csv(colunas, linhas, nome):
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(colunas)
    escritor.writerows(linhas)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"inline; filename={nome}.csv"},
    )


@app.route("/exportar/<tabela>.csv")
def exportar(tabela):
    _autorizar()
    if tabela not in TABELAS:
        abort(404)
    con = db()
    # O nome da tabela vem da lista TABELAS acima, nunca do usuário diretamente.
    cur = con.execute(f"SELECT * FROM {tabela}")
    colunas = [c[0] for c in cur.description]
    linhas = [tuple(linha) for linha in cur.fetchall()]
    con.close()
    return _resposta_csv(colunas, linhas, tabela)


# ---------------------------------------------------------------------------
# Resumos agregados: o cálculo é feito no banco e o resultado é pequeno.
# ---------------------------------------------------------------------------

def _resumo_mensal(con):
    colunas = ["mes", "unidade", "agendados", "realizados", "nao_compareceu",
               "cancelados", "bruto", "glosa", "liquido", "recebido", "fixo", "variavel"]

    agenda = con.execute("""
        SELECT substr(a.data_hora_agendada, 1, 7) AS mes, u.nome AS unidade,
               COUNT(*) AS agendados,
               SUM(a.status = 'Realizado') AS realizados,
               SUM(a.status = 'Não compareceu') AS nao_compareceu,
               SUM(a.status = 'Cancelado') AS cancelados
        FROM agendamentos a
        JOIN unidades u ON u.id_unidade = a.id_unidade
        GROUP BY mes, unidade
    """).fetchall()

    financeiro = con.execute("""
        SELECT substr(f.data_emissao, 1, 7) AS mes, u.nome AS unidade,
               SUM(f.valor_bruto) AS bruto,
               SUM(f.valor_glosa) AS glosa,
               SUM(f.valor_liquido) AS liquido,
               SUM(CASE WHEN f.data_recebimento IS NOT NULL THEN f.valor_liquido ELSE 0 END) AS recebido
        FROM faturamento f
        JOIN atendimentos at ON at.id_atendimento = f.id_atendimento
        JOIN agendamentos a ON a.id_agendamento = at.id_agendamento
        JOIN unidades u ON u.id_unidade = a.id_unidade
        GROUP BY mes, unidade
    """).fetchall()

    custos = con.execute("""
        SELECT substr(d.competencia, 1, 7) AS mes, u.nome AS unidade,
               SUM(CASE WHEN d.tipo = 'Fixo' THEN d.valor ELSE 0 END) AS fixo,
               SUM(CASE WHEN d.tipo = 'Variável' THEN d.valor ELSE 0 END) AS variavel
        FROM despesas d
        JOIN unidades u ON u.id_unidade = d.id_unidade
        GROUP BY mes, unidade
    """).fetchall()

    grade = {}

    def linha(mes, unidade):
        return grade.setdefault((mes, unidade), dict.fromkeys(colunas[2:], 0))

    for r in agenda:
        d = linha(r["mes"], r["unidade"])
        for c in ("agendados", "realizados", "nao_compareceu", "cancelados"):
            d[c] = r[c] or 0
    for r in financeiro:
        d = linha(r["mes"], r["unidade"])
        for c in ("bruto", "glosa", "liquido", "recebido"):
            d[c] = round(r[c] or 0, 2)
    for r in custos:
        d = linha(r["mes"], r["unidade"])
        for c in ("fixo", "variavel"):
            d[c] = round(r[c] or 0, 2)

    linhas = [(mes, unidade, *d.values()) for (mes, unidade), d in sorted(grade.items())]
    return colunas, linhas


def _resumo_especialidade(con):
    colunas = ["mes", "unidade", "especialidade", "realizados", "nao_compareceu"]
    linhas = con.execute("""
        SELECT substr(a.data_hora_agendada, 1, 7) AS mes, u.nome AS unidade,
               e.nome AS especialidade,
               SUM(a.status = 'Realizado') AS realizados,
               SUM(a.status = 'Não compareceu') AS nao_compareceu
        FROM agendamentos a
        JOIN unidades u ON u.id_unidade = a.id_unidade
        JOIN medicos m ON m.id_medico = a.id_medico
        JOIN especialidades e ON e.id_especialidade = m.id_especialidade
        GROUP BY mes, unidade, especialidade
        ORDER BY mes, unidade, especialidade
    """).fetchall()
    return colunas, [tuple(r) for r in linhas]


def _resumo_canal(con):
    colunas = ["mes", "unidade", "canal", "agendados"]
    linhas = con.execute("""
        SELECT substr(a.data_hora_agendada, 1, 7) AS mes, u.nome AS unidade,
               a.canal AS canal, COUNT(*) AS agendados
        FROM agendamentos a
        JOIN unidades u ON u.id_unidade = a.id_unidade
        GROUP BY mes, unidade, canal
        ORDER BY mes, unidade, canal
    """).fetchall()
    return colunas, [tuple(r) for r in linhas]


def _resumo_convenio(con):
    colunas = ["mes", "unidade", "convenio", "bruto", "glosa", "liquido"]
    linhas = con.execute("""
        SELECT substr(f.data_emissao, 1, 7) AS mes, u.nome AS unidade,
               c.nome AS convenio,
               ROUND(SUM(f.valor_bruto), 2) AS bruto,
               ROUND(SUM(f.valor_glosa), 2) AS glosa,
               ROUND(SUM(f.valor_liquido), 2) AS liquido
        FROM faturamento f
        JOIN atendimentos at ON at.id_atendimento = f.id_atendimento
        JOIN agendamentos a ON a.id_agendamento = at.id_agendamento
        JOIN unidades u ON u.id_unidade = a.id_unidade
        JOIN convenios c ON c.id_convenio = f.id_convenio
        GROUP BY mes, unidade, convenio
        ORDER BY mes, unidade, convenio
    """).fetchall()
    return colunas, [tuple(r) for r in linhas]


RESUMOS = {
    "mensal": _resumo_mensal,
    "especialidade": _resumo_especialidade,
    "canal": _resumo_canal,
    "convenio": _resumo_convenio,
}


@app.route("/exportar/resumo/<nome>.csv")
def exportar_resumo(nome):
    _autorizar()
    gerador = RESUMOS.get(nome)
    if gerador is None:
        abort(404)
    con = db()
    colunas, linhas = gerador(con)
    con.close()
    return _resposta_csv(colunas, linhas, f"resumo_{nome}")
