"""
Gera o banco fictício da rede Vitta Clínicas (SQLite).

Uso:   python gerar_dados.py
Saída: clinicas.db (na mesma pasta deste arquivo)

Cobre 24 meses de operação (dez/2024 a nov/2026) mais a agenda futura de dez/2026.
"""
import bisect
import os
import random
import sqlite3
from datetime import date, datetime, time, timedelta

random.seed(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "clinicas.db")

HOJE = date(2026, 11, 24)
INICIO = date(2024, 12, 1)
FIM = date(2026, 12, 31)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE unidades (
    id_unidade       INTEGER PRIMARY KEY,
    nome             TEXT,
    cidade           TEXT,
    uf               TEXT,
    data_inauguracao TEXT,
    num_salas        INTEGER
);
CREATE TABLE especialidades (
    id_especialidade INTEGER PRIMARY KEY,
    nome             TEXT
);
CREATE TABLE procedimentos (
    id_procedimento  INTEGER PRIMARY KEY,
    nome             TEXT,
    id_especialidade INTEGER REFERENCES especialidades,
    duracao_min      INTEGER,
    valor_base       REAL
);
CREATE TABLE medicos (
    id_medico        INTEGER PRIMARY KEY,
    nome             TEXT,
    crm              TEXT,
    uf_crm           TEXT,
    id_especialidade INTEGER REFERENCES especialidades,
    id_unidade       INTEGER REFERENCES unidades,
    data_admissao    TEXT,
    ativo            INTEGER
);
CREATE TABLE convenios (
    id_convenio             INTEGER PRIMARY KEY,
    nome                    TEXT,
    tipo                    TEXT,
    glosa_media             REAL,
    prazo_recebimento_dias  INTEGER
);
CREATE TABLE pacientes (
    id_paciente     INTEGER PRIMARY KEY,
    nome            TEXT,
    sexo            TEXT,
    data_nascimento TEXT,
    cidade          TEXT,
    uf              TEXT,
    id_convenio     INTEGER REFERENCES convenios,
    data_cadastro   TEXT
);
CREATE TABLE agendamentos (
    id_agendamento      INTEGER PRIMARY KEY,
    id_paciente         INTEGER REFERENCES pacientes,
    id_medico           INTEGER REFERENCES medicos,
    id_unidade          INTEGER REFERENCES unidades,
    id_procedimento     INTEGER REFERENCES procedimentos,
    data_criacao        TEXT,
    data_hora_agendada  TEXT,
    canal               TEXT,
    status              TEXT,
    motivo_cancelamento TEXT
);
CREATE TABLE atendimentos (
    id_atendimento     INTEGER PRIMARY KEY,
    id_agendamento     INTEGER UNIQUE REFERENCES agendamentos,
    data_hora_chegada  TEXT,
    data_hora_inicio   TEXT,
    data_hora_fim      TEXT
);
CREATE TABLE faturamento (
    id_faturamento   INTEGER PRIMARY KEY,
    id_atendimento   INTEGER UNIQUE REFERENCES atendimentos,
    id_convenio      INTEGER REFERENCES convenios,
    valor_bruto      REAL,
    valor_glosa      REAL,
    valor_liquido    REAL,
    data_emissao     TEXT,
    data_recebimento TEXT,
    forma_pagamento  TEXT
);
CREATE TABLE despesas (
    id_despesa   INTEGER PRIMARY KEY,
    id_unidade   INTEGER REFERENCES unidades,
    competencia  TEXT,
    categoria    TEXT,
    tipo         TEXT,
    valor        REAL
);
"""

UNIDADES = [
    # id, nome, cidade, uf, inauguração, salas
    (1, "Vitta Paulista", "São Paulo", "SP", "2019-03-04", 12),
    (2, "Vitta Campinas", "Campinas", "SP", "2020-08-17", 9),
    (3, "Vitta Copacabana", "Rio de Janeiro", "RJ", "2019-10-07", 10),
    (4, "Vitta Savassi", "Belo Horizonte", "MG", "2021-02-22", 8),
    (5, "Vitta Batel", "Curitiba", "PR", "2020-05-11", 8),
    (6, "Vitta Moinhos", "Porto Alegre", "RS", "2022-01-10", 7),
    (7, "Vitta Barra", "Salvador", "BA", "2024-03-11", 9),
    (8, "Vitta Boa Viagem", "Recife", "PE", "2025-02-03", 8),
    (9, "Vitta Asa Sul", "Brasília", "DF", "2025-09-15", 7),
    (10, "Vitta Meireles", "Fortaleza", "CE", "2026-04-06", 6),
]

ESPECIALIDADES = ["Clínica Geral", "Cardiologia", "Dermatologia",
                  "Ortopedia", "Pediatria", "Ginecologia"]

PROCEDIMENTOS = [
    # id, nome, especialidade, duração (min), valor base (R$)
    (1, "Consulta clínica", 1, 30, 220.0),
    (2, "Check-up anual", 1, 60, 480.0),
    (3, "Consulta cardiológica", 2, 40, 350.0),
    (4, "Eletrocardiograma", 2, 20, 180.0),
    (5, "Consulta dermatológica", 3, 30, 290.0),
    (6, "Biópsia de pele", 3, 45, 620.0),
    (7, "Consulta ortopédica", 4, 30, 320.0),
    (8, "Infiltração articular", 4, 30, 540.0),
    (9, "Consulta pediátrica", 5, 30, 260.0),
    (10, "Vacinação", 5, 15, 150.0),
    (11, "Consulta ginecológica", 6, 35, 300.0),
    (12, "Ultrassom obstétrico", 6, 40, 410.0),
]

CONVENIOS = [
    # id, nome, tipo, glosa média, prazo de recebimento (dias)
    (1, "Particular", "Particular", 0.0, 2),
    (2, "Saúde Plena", "Convênio", 0.06, 30),
    (3, "Vitalis Saúde", "Convênio", 0.09, 45),
    (4, "Bem Estar Convênios", "Convênio", 0.04, 60),
    (5, "Previda Saúde", "Convênio", 0.11, 60),
]
CONV = {c[0]: c for c in CONVENIOS}
PESO_CONVENIO = [(1, 45), (2, 20), (3, 15), (4, 10), (5, 10)]

CANAIS = [("Recepção", 35), ("Telefone", 25), ("App", 25), ("Site", 15)]
MOTIVOS_CANCELAMENTO = ["Paciente desmarcou", "Médico indisponível",
                        "Remarcado pelo paciente", "Convênio não autorizou"]

PRIMEIROS = ["Ana", "Beatriz", "Carla", "Daniela", "Eduarda", "Fernanda", "Gabriela",
             "Helena", "Isabela", "Juliana", "Larissa", "Mariana", "Natália", "Patrícia",
             "Rafaela", "Sofia", "Tatiane", "Vitória", "Bruno", "Carlos", "Diego",
             "Eduardo", "Felipe", "Gustavo", "Henrique", "Igor", "João", "Lucas",
             "Marcelo", "Rafael", "Renan", "Thiago", "Vinícius", "Ricardo", "Paulo",
             "Leonardo", "Alice", "Laura", "Cecília", "Valentina", "Arthur", "Miguel"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves",
              "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho",
              "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha",
              "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Cardoso", "Teixeira"]

HORARIOS = [time(h, m) for h in range(8, 18) for m in (0, 30)]


def nome_pessoa():
    return f"{random.choice(PRIMEIROS)} {random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"


def escolha_ponderada(opcoes):
    valores, pesos = zip(*opcoes)
    return random.choices(valores, weights=pesos, k=1)[0]


def data_aleatoria(ini, fim):
    return ini + timedelta(days=random.randint(0, (fim - ini).days))


def iso_dt(d):
    return d.strftime("%Y-%m-%d %H:%M")


def gerar_equipe():
    medicos, por_unidade = [], {}
    mid = 0
    for uid, _, _, uf, inaug, _ in UNIDADES:
        ini = date.fromisoformat(inaug)
        por_unidade[uid] = []
        for _ in range(5):
            mid += 1
            prefixo = random.choice(["Dr.", "Dra."])
            esp = random.randint(1, len(ESPECIALIDADES))
            admissao = ini + timedelta(days=random.randint(0, 30))
            tupla = (mid, f"{prefixo} {nome_pessoa()}", str(random.randint(10000, 99999)),
                     uf, esp, uid, admissao.isoformat(), 1)
            medicos.append(tupla)
            por_unidade[uid].append(tupla)
    return medicos, por_unidade


def gerar_pacientes(n):
    brutos = []
    for _ in range(n):
        sexo = random.choice(["F", "M"])
        nasc = data_aleatoria(date(1940, 1, 1), date(2024, 12, 31))
        cidade = random.choice(UNIDADES)
        conv = escolha_ponderada(PESO_CONVENIO)
        cad = data_aleatoria(date(2019, 1, 1), HOJE)
        brutos.append([sexo, nasc, cidade[2], cidade[3], conv, cad])
    # Ordenar por data de cadastro permite sortear só pacientes já cadastrados no dia.
    brutos.sort(key=lambda p: p[5])
    pacientes = []
    for i, (sexo, nasc, cid, uf, conv, cad) in enumerate(brutos, start=1):
        pacientes.append((i, nome_pessoa(), sexo, nasc.isoformat(), cid, uf, conv, cad.isoformat()))
    return pacientes


def gerar_despesas(cur, receita_mes):
    meses = []
    m = date(2024, 12, 1)
    while m <= date(2026, 11, 1):
        meses.append(m)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)

    linhas, did = [], 0
    for uid, _, _, _, inaug, salas in UNIDADES:
        ini = date.fromisoformat(inaug).replace(day=1)
        for mes in meses:
            if mes < ini:
                continue
            receita = receita_mes.get((uid, mes), 0.0)
            itens = [
                ("Aluguel", "Fixo", (15000 + 1500 * salas) * random.uniform(0.97, 1.03)),
                ("Folha administrativa", "Fixo", (12000 + 1200 * salas) * random.uniform(0.97, 1.03)),
                ("Energia, sistemas e outros", "Fixo", (3500 + 150 * salas) * random.uniform(0.97, 1.03)),
                ("Honorários médicos", "Variável", receita * 0.32),
                ("Insumos e materiais", "Variável", receita * 0.06),
                ("Impostos", "Variável", receita * 0.04),
            ]
            for cat, tipo, valor in itens:
                did += 1
                linhas.append((did, uid, mes.isoformat(), cat, tipo, round(valor, 2)))
    cur.executemany("INSERT INTO despesas VALUES (?,?,?,?,?,?)", linhas)


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cur = con.cursor()

    cur.executemany("INSERT INTO unidades VALUES (?,?,?,?,?,?)", UNIDADES)
    cur.executemany("INSERT INTO especialidades VALUES (?,?)",
                    [(i + 1, n) for i, n in enumerate(ESPECIALIDADES)])
    cur.executemany("INSERT INTO procedimentos VALUES (?,?,?,?,?)", PROCEDIMENTOS)
    cur.executemany("INSERT INTO convenios VALUES (?,?,?,?,?)", CONVENIOS)

    medicos, medicos_por_unidade = gerar_equipe()
    cur.executemany("INSERT INTO medicos VALUES (?,?,?,?,?,?,?,?)", medicos)

    pacientes = gerar_pacientes(14000)
    cur.executemany("INSERT INTO pacientes VALUES (?,?,?,?,?,?,?,?)", pacientes)
    cad_strs = [p[7] for p in pacientes]  # ordenado

    procs_por_esp = {}
    for p in PROCEDIMENTOS:
        procs_por_esp.setdefault(p[2], []).append(p)

    ag_rows, at_rows, fat_rows = [], [], []
    receita_mes = {}
    ids = {"ag": 0, "at": 0, "fat": 0}
    ocupados = set()

    dia = INICIO
    while dia <= FIM:
        dow = dia.weekday()  # 6 = domingo, sem atendimento
        if dow != 6:
            faixa = (18, 30) if dow < 5 else (8, 14)
            meses_decorridos = (dia.year - INICIO.year) * 12 + dia.month - INICIO.month
            fator = 1 + 0.01 * meses_decorridos  # crescimento orgânico de volume
            k = bisect.bisect_right(cad_strs, dia.isoformat())

            for uid, _, _, _, inaug, _ in UNIDADES:
                if date.fromisoformat(inaug) > dia:
                    continue
                for _ in range(int(random.randint(*faixa) * fator)):
                    medico = random.choice(medicos_por_unidade[uid])
                    proc = random.choice(procs_por_esp[medico[4]])
                    dt_ag = datetime.combine(dia, random.choice(HORARIOS))
                    if (medico[0], dt_ag) in ocupados:
                        continue
                    ocupados.add((medico[0], dt_ag))
                    pac = pacientes[random.randrange(k)]

                    ids["ag"] += 1
                    id_ag = ids["ag"]

                    r = random.random()
                    if r < 0.25:
                        criacao = dt_ag - timedelta(hours=random.randint(1, 72))
                    elif r < 0.70:
                        criacao = dt_ag - timedelta(days=random.randint(1, 7))
                    else:
                        criacao = dt_ag - timedelta(days=random.randint(8, 45))

                    canal = escolha_ponderada(CANAIS)
                    motivo = None
                    if dia < HOJE:
                        r = random.random()
                        if r < 0.80:
                            status = "Realizado"
                        elif r < 0.89:
                            status = "Cancelado"
                            motivo = random.choice(MOTIVOS_CANCELAMENTO)
                        else:
                            status = "Não compareceu"
                    else:
                        status = escolha_ponderada([("Confirmado", 70), ("Agendado", 30)])

                    ag_rows.append((id_ag, pac[0], medico[0], uid, proc[0],
                                    iso_dt(criacao), iso_dt(dt_ag), canal, status, motivo))

                    if status == "Realizado":
                        ids["at"] += 1
                        id_at = ids["at"]
                        chegada = dt_ag + timedelta(minutes=random.randint(-10, 20))
                        inicio = chegada + timedelta(minutes=random.randint(0, 35))
                        fim = inicio + timedelta(minutes=proc[3] + random.randint(-5, 10))
                        at_rows.append((id_at, id_ag, iso_dt(chegada), iso_dt(inicio), iso_dt(fim)))

                        conv = CONV[pac[6]]
                        bruto = round(proc[4] * random.uniform(0.95, 1.10), 2)
                        glosa = round(bruto * conv[3] * random.uniform(0.5, 1.5), 2)
                        liquido = round(bruto - glosa, 2)

                        if conv[2] == "Particular":
                            emissao = fim.date()
                            receb = emissao + timedelta(days=random.randint(0, 2))
                            forma = escolha_ponderada([("Pix", 45), ("Cartão de crédito", 25),
                                                       ("Cartão de débito", 15), ("Dinheiro", 15)])
                        else:
                            emissao = fim.date() + timedelta(days=random.randint(7, 20))
                            receb = emissao + timedelta(days=max(0, conv[4] + random.randint(-3, 5)))
                            forma = "Repasse convênio"
                            if random.random() < 0.03:  # convênios que ainda não pagaram
                                receb = None

                        emissao = min(emissao, HOJE)
                        if receb is not None and receb > HOJE:
                            receb = None
                        forma = forma if receb else None

                        ids["fat"] += 1
                        fat_rows.append((ids["fat"], id_at, conv[0], bruto, glosa, liquido,
                                         emissao.isoformat(),
                                         receb.isoformat() if receb else None, forma))

                        chave = (uid, dia.replace(day=1))
                        receita_mes[chave] = receita_mes.get(chave, 0.0) + liquido
        dia += timedelta(days=1)

    cur.executemany("INSERT INTO agendamentos VALUES (?,?,?,?,?,?,?,?,?,?)", ag_rows)
    cur.executemany("INSERT INTO atendimentos VALUES (?,?,?,?,?)", at_rows)
    cur.executemany("INSERT INTO faturamento VALUES (?,?,?,?,?,?,?,?,?)", fat_rows)
    gerar_despesas(cur, receita_mes)

    cur.executescript("""
        CREATE INDEX idx_ag_data   ON agendamentos(data_hora_agendada);
        CREATE INDEX idx_ag_medico ON agendamentos(id_medico);
        CREATE INDEX idx_ag_unid   ON agendamentos(id_unidade);
        CREATE INDEX idx_fat_at    ON faturamento(id_atendimento);
    """)
    con.commit()

    print("Banco criado em:", DB_PATH, "\n")
    tabelas = ["unidades", "especialidades", "procedimentos", "medicos", "convenios",
               "pacientes", "agendamentos", "atendimentos", "faturamento", "despesas"]
    for t in tabelas:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<17}{n:>9,}".replace(",", "."))
    con.close()


if __name__ == "__main__":
    main()
