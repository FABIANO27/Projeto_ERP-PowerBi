"""
Exportação das tabelas do ERP em CSV, para o Power BI (conector Web).

Rota: GET /exportar/<tabela>.csv
Cabeçalho obrigatório: X-Token: <valor da variável EXPORT_TOKEN>

Este módulo reaproveita o app do app.py. No Render, o Start Command
passa a apontar para exportacao:app.
"""
import csv
import hmac
import io
import os

from flask import Response, abort, request

from app import app, db

TOKEN = os.environ.get("EXPORT_TOKEN", "")

# Lista fechada: só estas tabelas podem ser exportadas.
TABELAS = {
    "agendamentos", "atendimentos", "faturamento", "despesas",
    "unidades", "medicos", "especialidades", "procedimentos",
    "convenios", "pacientes",
}


@app.route("/exportar/<tabela>.csv")
def exportar(tabela):
    if not TOKEN:
        abort(503)  # exportação desligada enquanto EXPORT_TOKEN não estiver definido
    enviado = request.headers.get("X-Token", "")
    if not hmac.compare_digest(enviado.encode(), TOKEN.encode()):
        abort(401)
    if tabela not in TABELAS:
        abort(404)

    con = db()
    # O nome da tabela vem da lista TABELAS acima, nunca do usuário diretamente.
    cur = con.execute(f"SELECT * FROM {tabela}")
    colunas = [c[0] for c in cur.description]
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(colunas)
    escritor.writerows(tuple(linha) for linha in cur.fetchall())
    con.close()

    return Response(
        buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"inline; filename={tabela}.csv"},
    )
