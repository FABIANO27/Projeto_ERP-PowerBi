"""
Vitta ERP: registro de agendamento e atendimento.

Instalar:  pip install flask
Rodar:     cd erp && python app.py
Acessar:   http://127.0.0.1:5000

Fluxo do agendamento:
  Agendado -> Confirmado -> Na recepção -> Em atendimento -> Realizado
  (ou Cancelado / Não compareceu a partir de Agendado ou Confirmado)
Ao finalizar, o atendimento gera o faturamento, que é recebido depois em /faturamento.
"""
import os
import sqlite3
from datetime import date, datetime

from flask import (Flask, abort, flash, redirect, render_template_string,
                   request, url_for)

DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "clinicas.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-troque-em-producao")

# ação -> (status de origem permitidos, status novo)
TRANSICOES = {
    "confirmar":      ({"Agendado"}, "Confirmado"),
    "chegou":         ({"Agendado", "Confirmado"}, "Na recepção"),
    "iniciar":        ({"Na recepção"}, "Em atendimento"),
    "finalizar":      ({"Em atendimento"}, "Realizado"),
    "cancelar":       ({"Agendado", "Confirmado"}, "Cancelado"),
    "nao_compareceu": ({"Agendado", "Confirmado"}, "Não compareceu"),
}

BOTOES = {
    "confirmar": "Confirmar",
    "chegou": "Chegou",
    "iniciar": "Iniciar atendimento",
    "finalizar": "Finalizar",
    "cancelar": "Cancelar",
    "nao_compareceu": "Não compareceu",
}

ACOES_POR_STATUS = {
    "Agendado": ["confirmar", "chegou", "cancelar", "nao_compareceu"],
    "Confirmado": ["chegou", "cancelar", "nao_compareceu"],
    "Na recepção": ["iniciar"],
    "Em atendimento": ["finalizar"],
}

HORARIOS = [f"{h:02d}:{m:02d}" for h in range(8, 18) for m in (0, 30)]
CANAIS = ["Recepção", "Telefone", "App", "Site"]
FORMAS = ["Pix", "Cartão de crédito", "Cartão de débito", "Dinheiro", "Repasse convênio"]


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def faturar(con, id_agendamento, id_procedimento, id_paciente, quando):
    """Cria o faturamento a partir do atendimento finalizado."""
    valor = con.execute(
        "SELECT valor_base FROM procedimentos WHERE id_procedimento = ?",
        (id_procedimento,)).fetchone()[0]
    id_convenio = con.execute(
        "SELECT id_convenio FROM pacientes WHERE id_paciente = ?",
        (id_paciente,)).fetchone()[0]
    id_at = con.execute(
        "SELECT id_atendimento FROM atendimentos WHERE id_agendamento = ?",
        (id_agendamento,)).fetchone()[0]
    # Glosa e recebimento entram depois, no lote do convênio e na baixa.
    con.execute(
        """INSERT INTO faturamento
           (id_atendimento, id_convenio, valor_bruto, valor_glosa, valor_liquido,
            data_emissao, data_recebimento, forma_pagamento)
           VALUES (?, ?, ?, 0, ?, ?, NULL, NULL)""",
        (id_at, id_convenio, valor, valor, quando[:10]))


BASE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }} · Vitta ERP</title>
<style>
  :root{
    --papel:#EEF2EF; --tinta:#1D2B2A; --suave:#5F6F6B;
    --verde:#2F6F5E; --verde-claro:#DCE9E3; --alerta:#B5492C;
    --branco:#FFFFFF; --linha:#D3DDD8;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--papel);color:var(--tinta);
       font:15px/1.5 "Avenir Next","Segoe UI",system-ui,sans-serif}
  header{display:flex;flex-wrap:wrap;gap:8px 32px;align-items:baseline;
         padding:18px 32px;border-bottom:1px solid var(--linha);background:var(--branco)}
  header h1{margin:0;font:600 22px/1 Charter,"Bitstream Charter",Georgia,serif;color:var(--verde)}
  nav a{color:var(--tinta);text-decoration:none;margin-right:20px;padding-bottom:3px}
  nav a.ativo{border-bottom:2px solid var(--verde)}
  main{padding:28px 32px;max-width:1200px}
  h2{margin:0 0 18px;font:500 26px/1.2 Charter,Georgia,serif}
  table{width:100%;border-collapse:collapse;background:var(--branco)}
  th,td{padding:10px 12px;border-bottom:1px solid var(--linha);text-align:left;vertical-align:top}
  th{color:var(--suave);font-size:13px;font-weight:600}
  td.hora{font-variant-numeric:tabular-nums;width:64px}
  .chip{display:inline-block;padding:2px 8px;border-radius:3px;background:var(--verde-claro);font-size:13px}
  .chip.alerta{background:#F6DDD4;color:var(--alerta)}
  form.campos{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
              gap:14px 18px;background:var(--branco);padding:20px;border:1px solid var(--linha)}
  label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--suave)}
  input,select{font:inherit;padding:8px 10px;border:1px solid #B9C7C1;background:#fff;color:var(--tinta)}
  button{font:inherit;padding:7px 12px;border:1px solid var(--verde);background:var(--verde);color:#fff;cursor:pointer}
  button.sec{background:#fff;color:var(--verde)}
  button.perigo{background:#fff;color:var(--alerta);border-color:var(--alerta)}
  .aviso{padding:10px 14px;background:var(--verde-claro);margin-bottom:18px}
  .acoes form{display:inline-block;margin:2px 4px 2px 0}
  .acoes button{padding:4px 9px;font-size:13px}
  .resumo{margin:0 0 14px;color:var(--suave)}
  :focus-visible{outline:2px solid var(--verde);outline-offset:2px}
</style>
</head>
<body>
<header>
  <h1>Vitta ERP</h1>
  <nav>
    <a href="{{ url_for('agenda') }}" class="{{ 'ativo' if secao == 'agenda' }}">Agenda</a>
    <a href="{{ url_for('novo') }}" class="{{ 'ativo' if secao == 'novo' }}">Novo agendamento</a>
    <a href="{{ url_for('faturamento_lista') }}" class="{{ 'ativo' if secao == 'fat' }}">Faturamento</a>
  </nav>
</header>
<main>
  {% with msgs = get_flashed_messages() %}
    {% for m in msgs %}<div class="aviso">{{ m }}</div>{% endfor %}
  {% endwith %}
  {{ corpo|safe }}
</main>
</body>
</html>
"""

AGENDA_HTML = """
<h2>Agenda</h2>
<form method="get" class="campos" style="margin-bottom:18px">
  <label>Data
    <input type="date" name="data" value="{{ dia }}">
  </label>
  <label>Unidade
    <select name="unidade">
      <option value="">Todas</option>
      {% for u in unidades %}
        <option value="{{ u.id_unidade }}" {% if u.id_unidade|string == uid %}selected{% endif %}>{{ u.nome }}</option>
      {% endfor %}
    </select>
  </label>
  <div><button type="submit" class="sec">Filtrar</button></div>
</form>

<p class="resumo">{{ linhas|length }} agendamento(s) em {{ dia }}</p>

<table>
  <thead>
    <tr><th>Hora</th><th>Paciente</th><th>Médico</th><th>Procedimento</th>
        <th>Unidade</th><th>Status</th><th>Ações</th></tr>
  </thead>
  <tbody>
  {% for l in linhas %}
    <tr>
      <td class="hora">{{ l.data_hora_agendada[11:16] }}</td>
      <td>{{ l.paciente }}</td>
      <td>{{ l.medico }}</td>
      <td>{{ l.procedimento }}</td>
      <td>{{ l.unidade }}</td>
      <td><span class="chip {{ 'alerta' if l.status in ['Cancelado', 'Não compareceu'] }}">{{ l.status }}</span></td>
      <td class="acoes">
        {% for codigo in acoes.get(l.status, []) %}
          <form method="post" action="{{ url_for('acao', id=l.id_agendamento, acao=codigo) }}">
            <input type="hidden" name="data" value="{{ dia }}">
            <button class="{{ 'perigo' if codigo in ['cancelar', 'nao_compareceu'] else 'sec' }}">{{ botoes[codigo] }}</button>
          </form>
        {% endfor %}
      </td>
    </tr>
  {% else %}
    <tr><td colspan="7">Nenhum agendamento neste dia. <a href="{{ url_for('novo') }}">Criar agendamento</a></td></tr>
  {% endfor %}
  </tbody>
</table>
"""

NOVO_HTML = """
<h2>Novo agendamento</h2>
<form method="get" class="campos" style="margin-bottom:18px">
  <label>Buscar paciente pelo nome
    <input name="busca" value="{{ busca }}" placeholder="Ex.: Ana Silva">
  </label>
  <div><button type="submit" class="sec">Buscar</button></div>
</form>

{% if busca and not pacientes %}
  <p>Nenhum paciente encontrado para “{{ busca }}”.</p>
{% elif not busca %}
  <p class="resumo">Busque o paciente primeiro. Depois escolha o médico, o procedimento e o horário.</p>
{% endif %}

{% if pacientes %}
<form method="post" class="campos">
  <label>Paciente
    <select name="id_paciente" required>
      <option value="" disabled selected>Escolha um paciente</option>
      {% for p in pacientes %}
        <option value="{{ p.id_paciente }}">{{ p.nome }} · nasc. {{ p.data_nascimento }}</option>
      {% endfor %}
    </select>
  </label>
  <label>Médico
    <select name="id_medico" required>
      {% for m in medicos %}
        <option value="{{ m.id_medico }}">{{ m.nome }} · {{ m.esp }} · {{ m.unidade }}</option>
      {% endfor %}
    </select>
  </label>
  <label>Procedimento
    <select name="id_procedimento" required>
      {% for p in procs %}
        <option value="{{ p.id_procedimento }}">{{ p.nome }} · R$ {{ '%.2f'|format(p.valor_base) }}</option>
      {% endfor %}
    </select>
  </label>
  <label>Data
    <input type="date" name="data" value="{{ hoje }}" required>
  </label>
  <label>Horário
    <select name="hora" required>
      {% for h in horarios %}<option value="{{ h }}">{{ h }}</option>{% endfor %}
    </select>
  </label>
  <label>Canal de entrada
    <select name="canal">
      {% for c in canais %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
    </select>
  </label>
  <div><button type="submit">Agendar</button></div>
</form>
{% endif %}
"""

FATURAMENTO_HTML = """
<h2>Faturamento em aberto</h2>
<p class="resumo">{{ abertos|length }} título(s) aguardando recebimento ·
  R$ {{ '{:,.2f}'.format(total).replace(',', 'X').replace('.', ',').replace('X', '.') }} em aberto</p>
<table>
  <thead>
    <tr><th>Emissão</th><th>Paciente</th><th>Procedimento</th><th>Convênio</th>
        <th>Valor líquido</th><th>Registrar recebimento</th></tr>
  </thead>
  <tbody>
  {% for f in abertos %}
    <tr>
      <td>{{ f.data_emissao }}</td>
      <td>{{ f.paciente }}</td>
      <td>{{ f.procedimento }}</td>
      <td>{{ f.convenio }}</td>
      <td>R$ {{ '%.2f'|format(f.valor_liquido) }}</td>
      <td class="acoes">
        <form method="post" action="{{ url_for('receber', id=f.id_faturamento) }}">
          <select name="forma">
            {% for x in formas %}<option value="{{ x }}">{{ x }}</option>{% endfor %}
          </select>
          <button class="sec">Receber</button>
        </form>
      </td>
    </tr>
  {% else %}
    <tr><td colspan="6">Nenhum título em aberto.</td></tr>
  {% endfor %}
  </tbody>
</table>
"""


def pagina(conteudo, titulo, secao):
    return render_template_string(BASE, corpo=conteudo, titulo=titulo, secao=secao)


@app.route("/")
def inicio():
    return redirect(url_for("agenda"))


@app.route("/agenda")
def agenda():
    dia = request.args.get("data") or date.today().isoformat()
    uid = request.args.get("unidade", "")
    con = db()
    unidades = con.execute("SELECT id_unidade, nome FROM unidades ORDER BY id_unidade").fetchall()
    sql = """
        SELECT a.id_agendamento, a.data_hora_agendada, a.status,
               p.nome AS paciente, m.nome AS medico,
               pr.nome AS procedimento, u.nome AS unidade
        FROM agendamentos a
        JOIN pacientes p      ON p.id_paciente = a.id_paciente
        JOIN medicos m        ON m.id_medico = a.id_medico
        JOIN procedimentos pr ON pr.id_procedimento = a.id_procedimento
        JOIN unidades u       ON u.id_unidade = a.id_unidade
        WHERE date(a.data_hora_agendada) = ?
    """
    params = [dia]
    if uid:
        sql += " AND a.id_unidade = ?"
        params.append(uid)
    sql += " ORDER BY a.data_hora_agendada"
    linhas = con.execute(sql, params).fetchall()
    con.close()
    corpo = render_template_string(AGENDA_HTML, linhas=linhas, dia=dia, uid=uid,
                                   unidades=unidades, acoes=ACOES_POR_STATUS, botoes=BOTOES)
    return pagina(corpo, "Agenda", "agenda")


@app.route("/novo", methods=["GET", "POST"])
def novo():
    con = db()

    if request.method == "POST":
        f = request.form
        unidade = con.execute(
            "SELECT id_unidade FROM medicos WHERE id_medico = ?", (f["id_medico"],)).fetchone()
        horario = f"{f['data']} {f['hora']}"
        conflito = con.execute(
            """SELECT 1 FROM agendamentos
               WHERE id_medico = ? AND data_hora_agendada = ? AND status <> 'Cancelado'""",
            (f["id_medico"], horario)).fetchone()
        if conflito:
            con.close()
            flash("Esse médico já tem um agendamento nesse horário. Escolha outro.")
            return redirect(url_for("novo"))
        con.execute(
            """INSERT INTO agendamentos
               (id_paciente, id_medico, id_unidade, id_procedimento,
                data_criacao, data_hora_agendada, canal, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'Agendado')""",
            (f["id_paciente"], f["id_medico"], unidade["id_unidade"], f["id_procedimento"],
             agora(), horario, f["canal"]))
        con.commit()
        con.close()
        flash("Agendamento criado.")
        return redirect(url_for("agenda", data=f["data"]))

    busca = request.args.get("busca", "").strip()
    pacientes = []
    if busca:
        pacientes = con.execute(
            """SELECT id_paciente, nome, data_nascimento FROM pacientes
               WHERE nome LIKE ? ORDER BY nome LIMIT 50""",
            (f"%{busca}%",)).fetchall()
    medicos = con.execute(
        """SELECT m.id_medico, m.nome, e.nome AS esp, u.nome AS unidade
           FROM medicos m
           JOIN especialidades e ON e.id_especialidade = m.id_especialidade
           JOIN unidades u       ON u.id_unidade = m.id_unidade
           WHERE m.ativo = 1
           ORDER BY u.id_unidade, m.nome""").fetchall()
    procs = con.execute(
        "SELECT id_procedimento, nome, valor_base FROM procedimentos ORDER BY nome").fetchall()
    con.close()

    corpo = render_template_string(NOVO_HTML, busca=busca, pacientes=pacientes,
                                   medicos=medicos, procs=procs, canais=CANAIS,
                                   horarios=HORARIOS, hoje=date.today().isoformat())
    return pagina(corpo, "Novo agendamento", "novo")


@app.route("/agendamento/<int:id>/<acao>", methods=["POST"])
def acao(id, acao):
    if acao not in TRANSICOES:
        abort(404)
    origens, novo_status = TRANSICOES[acao]

    con = db()
    ag = con.execute(
        """SELECT status, data_hora_agendada, id_procedimento, id_paciente
           FROM agendamentos WHERE id_agendamento = ?""", (id,)).fetchone()
    if ag is None:
        con.close()
        abort(404)

    dia = request.form.get("data") or ag["data_hora_agendada"][:10]
    if ag["status"] not in origens:
        flash(f"Não é possível aplicar esta ação a um agendamento com status “{ag['status']}”.")
    else:
        t = agora()
        con.execute("UPDATE agendamentos SET status = ? WHERE id_agendamento = ?", (novo_status, id))
        if acao == "chegou":
            con.execute(
                """INSERT OR IGNORE INTO atendimentos (id_agendamento, data_hora_chegada)
                   VALUES (?, ?)""", (id, t))
        elif acao == "iniciar":
            con.execute(
                "UPDATE atendimentos SET data_hora_inicio = ? WHERE id_agendamento = ?", (t, id))
        elif acao == "finalizar":
            con.execute(
                "UPDATE atendimentos SET data_hora_fim = ? WHERE id_agendamento = ?", (t, id))
            faturar(con, id, ag["id_procedimento"], ag["id_paciente"], t)
        con.commit()
        flash(f"Agendamento atualizado: {novo_status}.")
    con.close()
    return redirect(url_for("agenda", data=dia))


@app.route("/faturamento")
def faturamento_lista():
    con = db()
    abertos = con.execute(
        """SELECT f.id_faturamento, f.data_emissao, f.valor_liquido,
                  c.nome AS convenio, p.nome AS paciente, pr.nome AS procedimento
           FROM faturamento f
           JOIN convenios c      ON c.id_convenio = f.id_convenio
           JOIN atendimentos at  ON at.id_atendimento = f.id_atendimento
           JOIN agendamentos a   ON a.id_agendamento = at.id_agendamento
           JOIN pacientes p      ON p.id_paciente = a.id_paciente
           JOIN procedimentos pr ON pr.id_procedimento = a.id_procedimento
           WHERE f.data_recebimento IS NULL
           ORDER BY f.data_emissao
           LIMIT 200""").fetchall()
    total = con.execute(
        """SELECT COALESCE(SUM(valor_liquido), 0) FROM faturamento
           WHERE data_recebimento IS NULL""").fetchone()[0]
    con.close()
    corpo = render_template_string(FATURAMENTO_HTML, abertos=abertos, total=total, formas=FORMAS)
    return pagina(corpo, "Faturamento", "fat")


@app.route("/faturamento/<int:id>/receber", methods=["POST"])
def receber(id):
    forma = request.form.get("forma")
    if forma not in FORMAS:
        abort(400)
    con = db()
    con.execute(
        """UPDATE faturamento SET data_recebimento = ?, forma_pagamento = ?
           WHERE id_faturamento = ? AND data_recebimento IS NULL""",
        (date.today().isoformat(), forma, id))
    con.commit()
    con.close()
    flash("Recebimento registrado.")
    return redirect(url_for("faturamento_lista"))


if __name__ == "__main__":
    if not os.path.exists(DB):
        print("Banco não encontrado. Rode antes: python ../gerar_dados.py")
    app.run(debug=True)
