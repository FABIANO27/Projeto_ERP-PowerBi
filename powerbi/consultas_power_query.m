// =====================================================================
// Power Query (M) — uma consulta por tabela.
// Crie cada uma em: Página Inicial > Obter Dados > Consulta em Branco
// e cole o código no Editor Avançado. Nomeie a consulta igual à tabela.
// Pré-requisito: DSN ODBC "ClinicasERP" apontando para clinicas.db
// (driver SQLite ODBC). Veja o README.
// =====================================================================

// ---------- agendamentos (fato) ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM agendamentos"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_agendamento", Int64.Type}, {"id_paciente", Int64.Type},
        {"id_medico", Int64.Type}, {"id_unidade", Int64.Type},
        {"id_procedimento", Int64.Type},
        {"data_criacao", type datetime}, {"data_hora_agendada", type datetime}}),
    ComData = Table.AddColumn(Tipos, "data_agenda", each DateTime.Date([data_hora_agendada]), type date)
in
    ComData

// ---------- atendimentos (fato) ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM atendimentos"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_atendimento", Int64.Type}, {"id_agendamento", Int64.Type},
        {"data_hora_chegada", type datetime},
        {"data_hora_inicio", type datetime},
        {"data_hora_fim", type datetime}})
in
    Tipos

// ---------- faturamento (fato) ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM faturamento"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_faturamento", Int64.Type}, {"id_atendimento", Int64.Type},
        {"id_convenio", Int64.Type},
        {"valor_bruto", type number}, {"valor_glosa", type number},
        {"valor_liquido", type number},
        {"data_emissao", type date}, {"data_recebimento", type date}})
in
    Tipos

// ---------- despesas (fato) ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM despesas"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_despesa", Int64.Type}, {"id_unidade", Int64.Type},
        {"competencia", type date}, {"valor", type number}})
in
    Tipos

// ---------- dim_unidade ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM unidades"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_unidade", Int64.Type}, {"data_inauguracao", type date}, {"num_salas", Int64.Type}})
in
    Tipos

// ---------- dim_medico (medicos + especialidade) ----------
let
    Medicos = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM medicos"),
    Esp = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM especialidades"),
    Juntar = Table.NestedJoin(Medicos, {"id_especialidade"}, Esp, {"id_especialidade"}, "esp", JoinKind.LeftOuter),
    Expandir = Table.ExpandTableColumn(Juntar, "esp", {"nome"}, {"especialidade"}),
    Tipos = Table.TransformColumnTypes(Expandir, {
        {"id_medico", Int64.Type}, {"id_unidade", Int64.Type}, {"data_admissao", type date}})
in
    Tipos

// ---------- dim_procedimento ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM procedimentos"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_procedimento", Int64.Type}, {"duracao_min", Int64.Type}, {"valor_base", type number}})
in
    Tipos

// ---------- dim_paciente (sem dados pessoais sensíveis além do necessário) ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT id_paciente, nome, sexo, data_nascimento, cidade, uf, id_convenio, data_cadastro FROM pacientes"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_paciente", Int64.Type}, {"id_convenio", Int64.Type},
        {"data_nascimento", type date}, {"data_cadastro", type date}})
in
    Tipos

// ---------- dim_convenio ----------
let
    Origem = Odbc.Query("dsn=ClinicasERP", "SELECT * FROM convenios"),
    Tipos = Table.TransformColumnTypes(Origem, {
        {"id_convenio", Int64.Type}, {"glosa_media", type number}, {"prazo_recebimento_dias", Int64.Type}})
in
    Tipos
