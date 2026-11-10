import hashlib
from html import escape as html_escape
import io
import os
import secrets
import string
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
import click
from flask import (
    Flask, abort, flash, redirect, render_template,
    request, send_file, session, url_for
)
from mysql.connector import IntegrityError, Error as MySQLError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
from config import DB_CONFIG

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)

PERFIS = {"paciente", "cuidador", "medico"}
CONTEXTOS_MEDICAO = {
    "jejum", "antes_refeicao", "apos_refeicao", "ao_deitar", "outro"
}


@contextmanager
def db_session():
    """Abre uma conexão/cursor e garante commit, rollback e fechamento."""
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor(dictionary=True)
    try:
        yield connection, cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def login_url_for_profile(perfil=None):
    perfil = perfil or session.get("perfil")
    return {
        "paciente": "inicio_paciente",
        "cuidador": "inicio_cuidador",
        "medico": "inicio_medico",
    }.get(perfil, "login")


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id, nome, email, perfil, ativo, medico_registro, medico_uf, medico_verificado "
            "FROM usuarios WHERE id = %s",
            (user_id,),
        )
        return cursor.fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Entre na sua conta para continuar.", "info")
            return redirect(url_for("login"))
        user = current_user()
        if not user or not user["ativo"]:
            session.clear()
            flash("Sua conta não está ativa. Entre em contato com a equipe responsável.", "error")
            return redirect(url_for("login"))
        # Mantém nome e perfil da sessão sincronizados com a conta no banco.
        session["nome"] = user["nome"]
        session["perfil"] = user["perfil"]
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("perfil") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def can_access_patient(patient_id, user=None):
    """Confere autorização no servidor; não confia no ID enviado pelo navegador."""
    user = user or current_user()
    if not user:
        return False
    if user["perfil"] == "paciente":
        return int(user["id"]) == int(patient_id)
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id FROM vinculos_cuidado "
            "WHERE paciente_id = %s AND usuario_vinculado_id = %s "
            "AND perfil_vinculado = %s AND status = 'ativo' LIMIT 1",
            (patient_id, user["id"], user["perfil"]),
        )
        return cursor.fetchone() is not None


def get_patient_record(patient_id):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id, nome, email FROM usuarios WHERE id = %s AND perfil = 'paciente' AND ativo = 1",
            (patient_id,),
        )
        return cursor.fetchone()


def linked_patients(user_id, perfil):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT u.id, u.nome, u.email, vc.criado_em "
            "FROM vinculos_cuidado vc "
            "JOIN usuarios u ON u.id = vc.paciente_id "
            "WHERE vc.usuario_vinculado_id = %s AND vc.perfil_vinculado = %s "
            "AND vc.status = 'ativo' AND u.ativo = 1 ORDER BY u.nome",
            (user_id, perfil),
        )
        return cursor.fetchall()


def get_measurements(patient_id, limit=12):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id, valor, unidade, contexto, medido_em, registrado_por, observacoes "
            "FROM medicoes_glicemia WHERE paciente_id = %s AND status = 'ativo' "
            "ORDER BY medido_em DESC LIMIT %s",
            (patient_id, limit),
        )
        return cursor.fetchall()


def get_tasks(patient_id, limit=10):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id, titulo, descricao, tipo, data_hora, status "
            "FROM tarefas WHERE paciente_id = %s ORDER BY "
            "CASE status WHEN 'pendente' THEN 0 ELSE 1 END, data_hora ASC LIMIT %s",
            (patient_id, limit),
        )
        return cursor.fetchall()


def get_appointments(patient_id, limit=8):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT c.id, c.data_hora, c.local, c.motivo, c.status, u.nome AS medico_nome "
            "FROM consultas c JOIN usuarios u ON u.id = c.medico_id "
            "WHERE c.paciente_id = %s AND c.status = 'agendada' AND c.data_hora >= NOW() "
            "ORDER BY c.data_hora ASC LIMIT %s",
            (patient_id, limit),
        )
        return cursor.fetchall()


def get_active_plan(patient_id):
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT pc.id, pc.titulo, pc.orientacoes, pc.metas, pc.atualizado_em, u.nome AS medico_nome "
            "FROM planos_cuidado pc JOIN usuarios u ON u.id = pc.medico_id "
            "WHERE pc.paciente_id = %s AND pc.ativo = 1 ORDER BY pc.atualizado_em DESC LIMIT 1",
            (patient_id,),
        )
        return cursor.fetchone()


def build_chart_points(measurements):
    ordered = list(reversed(measurements))
    max_value = max([float(item["valor"]) for item in ordered], default=1) or 1
    points = []
    for item in ordered:
        value = float(item["valor"])
        points.append({
            "label": item["medido_em"].strftime("%d/%m"),
            "valor": value,
            "altura": max(8, min(100, round(value / max_value * 100))),
        })
    return points



def log_audit(user_id, action, resource, resource_id=None, details=None):
    with db_session() as (_, cursor):
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user_id, action, resource, resource_id, (details or "")[:500] or None),
        )


def get_care_timeline(patient_id, limit=20):
    """Linha do tempo com medições, tarefas, consultas e planos compartilhados."""
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT * FROM ("
            " SELECT 'medicao' AS event_type, m.medido_em AS event_at, "
            " CONCAT(CAST(m.valor AS CHAR), ' ', m.unidade, ' · ', REPLACE(m.contexto, '_', ' ')) AS event_detail, "
            " u.nome AS actor "
            " FROM medicoes_glicemia m JOIN usuarios u ON u.id = m.registrado_por "
            " WHERE m.paciente_id = %s AND m.status = 'ativo' "
            " UNION ALL "
            " SELECT 'atividade' AS event_type, t.criado_em AS event_at, t.titulo AS event_detail, "
            " u.nome AS actor FROM tarefas t JOIN usuarios u ON u.id = t.criado_por WHERE t.paciente_id = %s "
            " UNION ALL "
            " SELECT 'consulta' AS event_type, c.criado_em AS event_at, "
            " CONCAT('Consulta · ', COALESCE(c.motivo, 'agendada')) AS event_detail, "
            " u.nome AS actor FROM consultas c JOIN usuarios u ON u.id = c.medico_id WHERE c.paciente_id = %s "
            " UNION ALL "
            " SELECT 'plano' AS event_type, pc.atualizado_em AS event_at, pc.titulo AS event_detail, "
            " u.nome AS actor FROM planos_cuidado pc JOIN usuarios u ON u.id = pc.medico_id WHERE pc.paciente_id = %s "
            ") AS care_events ORDER BY event_at DESC LIMIT %s",
            (patient_id, patient_id, patient_id, patient_id, limit),
        )
        return cursor.fetchall()

def get_dashboard_patient_data(patient_id):
    patient = get_patient_record(patient_id)
    if not patient:
        return None
    measurements = get_measurements(patient_id, 12)
    tasks = get_tasks(patient_id, 12)
    appointments = get_appointments(patient_id, 8)
    plan = get_active_plan(patient_id)
    pending_tasks = sum(1 for task in tasks if task["status"] == "pendente")
    last_measurement = measurements[0] if measurements else None
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT COUNT(*) AS total FROM medicoes_glicemia "
            "WHERE paciente_id = %s AND status = 'ativo' AND medido_em >= %s",
            (patient_id, datetime.now() - timedelta(days=7)),
        )
        weekly_total = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT vc.id, vc.perfil_vinculado, u.nome, u.email "
            "FROM vinculos_cuidado vc JOIN usuarios u ON u.id = vc.usuario_vinculado_id "
            "WHERE vc.paciente_id = %s AND vc.status = 'ativo' ORDER BY u.nome",
            (patient_id,),
        )
        network = cursor.fetchall()
    return {
        "patient": patient,
        "measurements": measurements,
        "chart_points": build_chart_points(measurements),
        "tasks": tasks,
        "appointments": appointments,
        "plan": plan,
        "pending_tasks": pending_tasks,
        "last_measurement": last_measurement,
        "weekly_total": weekly_total,
        "network": network,
        "timeline": get_care_timeline(patient_id, 20),
    }


def parse_datetime_local(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


@app.before_request
def csrf_protection():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, description="A sessão do formulário expirou. Atualize a página e tente novamente.")


@app.context_processor
def inject_template_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf_token"],
        "now_local": datetime.now(),
        "ano_atual": datetime.now().year,
        "perfil_label": {
            "paciente": "Paciente", "cuidador": "Cuidador(a)", "medico": "Médico(a)"
        }.get(session.get("perfil"), ""),
    }


@app.errorhandler(403)
def forbidden(_error):
    return render_template("erro.html", codigo=403,
                           titulo="Acesso não autorizado",
                           mensagem="Sua conta não tem permissão para acessar esta área."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("erro.html", codigo=404,
                           titulo="Página não encontrada",
                           mensagem="Não encontramos o endereço que você tentou acessar."), 404


@app.errorhandler(400)
def bad_request(error):
    message = getattr(error, "description", "Não foi possível processar esta solicitação.")
    return render_template("erro.html", codigo=400,
                           titulo="Não foi possível continuar", mensagem=message), 400


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/inicio")
@login_required
def index():
    return redirect(url_for(login_url_for_profile()))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for(login_url_for_profile()))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        if not email or not senha:
            flash("Informe seu e-mail e sua senha.", "error")
            return render_template("login.html")
        try:
            with db_session() as (_, cursor):
                cursor.execute(
                    "SELECT id, nome, email, senha_hash, perfil, ativo "
                    "FROM usuarios WHERE email = %s LIMIT 1", (email,)
                )
                user = cursor.fetchone()
        except MySQLError:
            app.logger.exception("Falha ao consultar usuário no banco.")
            flash("Não foi possível conectar ao banco de dados. Confira o arquivo .env.", "error")
            return render_template("login.html")
        if not user or not user["ativo"] or not check_password_hash(user["senha_hash"], senha):
            flash("E-mail ou senha incorretos.", "error")
            return render_template("login.html")
        session.clear()
        session["user_id"] = user["id"]
        session["nome"] = user["nome"]
        session["perfil"] = user["perfil"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash(f"Bem-vindo(a), {user['nome'].split()[0]}!", "success")
        return redirect(url_for(login_url_for_profile(user["perfil"])))
    return render_template("login.html")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if session.get("user_id"):
        return redirect(url_for(login_url_for_profile()))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        perfil = request.form.get("perfil", "").strip().lower()
        senha = request.form.get("senha", "")
        confirma = request.form.get("confirma_senha", "")
        data_nascimento = request.form.get("data_nascimento") or None
        telefone = request.form.get("telefone", "").strip() or None
        registro = request.form.get("medico_registro", "").strip() or None
        uf = request.form.get("medico_uf", "").strip().upper() or None

        if not nome or not email or perfil not in PERFIS:
            flash("Preencha nome, e-mail e selecione um perfil válido.", "error")
            return render_template("cadastro.html")
        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template("cadastro.html")
        if senha != confirma:
            flash("As senhas não coincidem.", "error")
            return render_template("cadastro.html")
        if perfil == "medico" and bool(registro) != bool(uf):
            flash("Para informar o registro profissional, preencha também a UF.", "error")
            return render_template("cadastro.html")
        try:
            with db_session() as (_, cursor):
                cursor.execute(
                    "INSERT INTO usuarios "
                    "(nome, email, senha_hash, perfil, data_nascimento, telefone, medico_registro, medico_uf) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (nome, email, generate_password_hash(senha), perfil,
                     data_nascimento, telefone, registro if perfil == "medico" else None,
                     uf if perfil == "medico" else None),
                )
                new_id = cursor.lastrowid
        except IntegrityError:
            flash("Este e-mail já possui cadastro. Entre na sua conta.", "error")
            return render_template("cadastro.html")
        except MySQLError:
            app.logger.exception("Falha ao cadastrar usuário.")
            flash("Não foi possível salvar seu cadastro. Confira a conexão com o banco.", "error")
            return render_template("cadastro.html")
        session.clear()
        session["user_id"] = new_id
        session["nome"] = nome
        session["perfil"] = perfil
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash("Conta criada com sucesso. Complete seu perfil e conecte sua rede de cuidado.", "success")
        return redirect(url_for(login_url_for_profile(perfil)))
    return render_template("cadastro.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Você saiu da sua conta.", "info")
    return redirect(url_for("landing"))


@app.route("/inicio-paciente")
@role_required("paciente")
def inicio_paciente():
    log_audit(session["user_id"], "acessar", "painel_paciente", session["user_id"])
    data = get_dashboard_patient_data(session["user_id"])
    return render_template("dashboard_paciente.html", data=data)


@app.route("/inicio-cuidador")
@role_required("cuidador")
def inicio_cuidador():
    patients = linked_patients(session["user_id"], "cuidador")
    selected_id = request.args.get("paciente_id", type=int)
    selected = next((p for p in patients if p["id"] == selected_id), None) if selected_id else None
    if not selected and patients:
        selected = patients[0]
    if selected:
        log_audit(session["user_id"], "acessar", "dados_paciente", selected["id"], "Acesso pelo cuidador vinculado")
    data = get_dashboard_patient_data(selected["id"]) if selected else None
    return render_template("dashboard_cuidador.html", patients=patients, selected=selected, data=data)


@app.route("/inicio-medico")
@role_required("medico")
def inicio_medico():
    patients = linked_patients(session["user_id"], "medico")
    selected_id = request.args.get("paciente_id", type=int)
    selected = next((p for p in patients if p["id"] == selected_id), None) if selected_id else None
    if not selected and patients:
        selected = patients[0]
    if selected:
        log_audit(session["user_id"], "acessar", "dados_paciente", selected["id"], "Acesso pelo médico vinculado")
    data = get_dashboard_patient_data(selected["id"]) if selected else None
    user = current_user()
    return render_template("dashboard_medico.html", patients=patients, selected=selected,
                           data=data, doctor=user)


@app.route("/medicoes/registrar", methods=["POST"])
@role_required("paciente", "cuidador")
def registrar_medicao():
    user = current_user()
    patient_id = int(request.form.get("paciente_id") or user["id"])
    if user["perfil"] == "paciente":
        patient_id = user["id"]
    if not can_access_patient(patient_id, user):
        abort(403)
    try:
        valor = float(request.form.get("valor", "").replace(",", "."))
    except ValueError:
        flash("Informe um valor numérico válido.", "error")
        return redirect(request.referrer or url_for("index"))
    contexto = request.form.get("contexto", "outro")
    medido_em = parse_datetime_local(request.form.get("medido_em")) or datetime.now()
    observacoes = request.form.get("observacoes", "").strip()[:1000] or None
    if valor <= 0 or valor > 2000 or contexto not in CONTEXTOS_MEDICAO:
        flash("Confira o valor e o contexto da medição.", "error")
        return redirect(request.referrer or url_for("index"))
    with db_session() as (_, cursor):
        cursor.execute(
            "INSERT INTO medicoes_glicemia "
            "(paciente_id, registrado_por, valor, unidade, contexto, medido_em, observacoes, origem) "
            "VALUES (%s, %s, %s, 'mg/dL', %s, %s, %s, 'manual')",
            (patient_id, user["id"], valor, contexto, medido_em, observacoes),
        )
        measurement_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'criar', 'medicao_glicemia', %s, %s)",
            (user["id"], measurement_id, f"Registro de medição para paciente {patient_id}"),
        )
    flash("Medição registrada e adicionada ao histórico.", "success")
    if user["perfil"] == "cuidador":
        return redirect(url_for("inicio_cuidador", paciente_id=patient_id))
    return redirect(url_for("inicio_paciente"))


@app.route("/tarefas/criar", methods=["POST"])
@role_required("paciente", "cuidador")
def criar_tarefa():
    user = current_user()
    patient_id = int(request.form.get("paciente_id") or user["id"])
    if user["perfil"] == "paciente":
        patient_id = user["id"]
    if not can_access_patient(patient_id, user):
        abort(403)
    titulo = request.form.get("titulo", "").strip()[:140]
    descricao = request.form.get("descricao", "").strip()[:500] or None
    tipo = request.form.get("tipo", "autocuidado")
    data_hora = parse_datetime_local(request.form.get("data_hora"))
    if not titulo or not data_hora or tipo not in {"medicao", "medicamento", "consulta", "exame", "autocuidado", "outro"}:
        flash("Preencha o título, o tipo e a data da atividade.", "error")
        return redirect(request.referrer or url_for("index"))
    with db_session() as (_, cursor):
        cursor.execute(
            "INSERT INTO tarefas (paciente_id, criado_por, titulo, descricao, tipo, data_hora) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (patient_id, user["id"], titulo, descricao, tipo, data_hora),
        )
        task_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'criar_tarefa', 'tarefa', %s, %s)",
            (user["id"], task_id, f"Atividade para paciente {patient_id}"),
        )
    flash("Atividade adicionada à rotina.", "success")
    if user["perfil"] == "cuidador":
        return redirect(url_for("inicio_cuidador", paciente_id=patient_id))
    return redirect(url_for("inicio_paciente"))


@app.route("/tarefas/<int:task_id>/concluir", methods=["POST"])
@role_required("paciente", "cuidador")
def concluir_tarefa(task_id):
    user = current_user()
    with db_session() as (_, cursor):
        cursor.execute("SELECT id, paciente_id FROM tarefas WHERE id = %s", (task_id,))
        task = cursor.fetchone()
        if not task or not can_access_patient(task["paciente_id"], user):
            abort(403)
        cursor.execute(
            "UPDATE tarefas SET status = 'concluida', concluida_por = %s, concluida_em = NOW() "
            "WHERE id = %s AND status = 'pendente'",
            (user["id"], task_id),
        )
        if cursor.rowcount:
            cursor.execute(
                "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
                "VALUES (%s, 'concluir_tarefa', 'tarefa', %s, %s)",
                (user["id"], task_id, f"Atividade do paciente {task['paciente_id']} concluída"),
            )
    flash("Atividade marcada como concluída.", "success")
    if user["perfil"] == "cuidador":
        return redirect(url_for("inicio_cuidador", paciente_id=task["paciente_id"]))
    return redirect(url_for("inicio_paciente"))


@app.route("/vinculos/gerar", methods=["POST"])
@role_required("paciente")
def gerar_convite():
    perfil_destino = request.form.get("perfil_destino", "")
    if perfil_destino not in {"cuidador", "medico"}:
        flash("Selecione se o convite é para cuidador ou médico.", "error")
        return redirect(url_for("inicio_paciente"))
    alphabet = string.ascii_uppercase + string.digits
    raw_code = "GC-" + "".join(secrets.choice(alphabet) for _ in range(8))
    token_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
    expires_at = datetime.now() + timedelta(days=7)
    with db_session() as (_, cursor):
        cursor.execute(
            "INSERT INTO convites_vinculo (paciente_id, criado_por, perfil_destino, token_hash, expira_em) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session["user_id"], session["user_id"], perfil_destino, token_hash, expires_at),
        )
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'gerar_convite', 'vinculo', %s, %s)",
            (session["user_id"], cursor.lastrowid, f"Convite para perfil {perfil_destino}"),
        )
    flash(f"Código de convite: {raw_code} · válido por 7 dias. Compartilhe somente com a pessoa autorizada.", "success")
    return redirect(url_for("inicio_paciente"))


@app.route("/vinculos/aceitar", methods=["POST"])
@role_required("cuidador", "medico")
def aceitar_convite():
    code = request.form.get("codigo", "").strip().upper().replace(" ", "")
    if not code:
        flash("Digite o código recebido do paciente.", "error")
        return redirect(url_for(login_url_for_profile()))
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    user = current_user()
    if user["perfil"] == "medico" and not user["medico_verificado"]:
        flash("Seu registro profissional ainda precisa ser validado pela equipe do GlicoCheck antes de vincular pacientes.", "error")
        return redirect(url_for("inicio_medico"))
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT id, paciente_id, perfil_destino, expira_em, utilizado_em "
            "FROM convites_vinculo WHERE token_hash = %s LIMIT 1 FOR UPDATE", (digest,)
        )
        invite = cursor.fetchone()
        if (not invite or invite["utilizado_em"] or invite["expira_em"] < datetime.now()
                or invite["perfil_destino"] != user["perfil"]):
            flash("Código inválido, expirado ou destinado a outro perfil.", "error")
            return redirect(url_for(login_url_for_profile()))
        cursor.execute(
            "INSERT INTO vinculos_cuidado "
            "(paciente_id, usuario_vinculado_id, perfil_vinculado, criado_por) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE status = 'ativo', atualizado_em = NOW()",
            (invite["paciente_id"], user["id"], user["perfil"], user["id"]),
        )
        cursor.execute(
            "UPDATE convites_vinculo SET utilizado_em = NOW(), utilizado_por = %s WHERE id = %s",
            (user["id"], invite["id"]),
        )
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'aceitar_convite', 'vinculo', %s, %s)",
            (user["id"], invite["id"], f"Vínculo com paciente {invite['paciente_id']}"),
        )
    flash("Vínculo criado. O paciente agora aparece na sua lista.", "success")
    return redirect(url_for(login_url_for_profile()))


@app.route("/planos/criar", methods=["POST"])
@role_required("medico")
def criar_plano():
    user = current_user()
    if not user["medico_verificado"]:
        flash("Seu registro profissional precisa ser validado antes de criar planos de cuidado.", "error")
        return redirect(url_for("inicio_medico"))
    patient_id = request.form.get("paciente_id", type=int)
    if not patient_id or not can_access_patient(patient_id, user):
        abort(403)
    titulo = request.form.get("titulo", "").strip()[:160]
    orientacoes = request.form.get("orientacoes", "").strip()[:5000]
    metas = request.form.get("metas", "").strip()[:2000] or None
    if not titulo or not orientacoes:
        flash("Informe o título e as orientações do plano.", "error")
        return redirect(url_for("inicio_medico", paciente_id=patient_id))
    with db_session() as (_, cursor):
        cursor.execute("UPDATE planos_cuidado SET ativo = 0 WHERE paciente_id = %s", (patient_id,))
        cursor.execute(
            "INSERT INTO planos_cuidado (paciente_id, medico_id, titulo, orientacoes, metas) "
            "VALUES (%s, %s, %s, %s, %s)",
            (patient_id, user["id"], titulo, orientacoes, metas),
        )
        new_plan_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'criar_plano', 'plano_cuidado', %s, %s)",
            (user["id"], new_plan_id, f"Plano para paciente {patient_id}"),
        )
    flash("Plano de cuidado salvo e disponibilizado para o paciente.", "success")
    return redirect(url_for("inicio_medico", paciente_id=patient_id))


@app.route("/consultas/criar", methods=["POST"])
@role_required("medico")
def criar_consulta():
    user = current_user()
    if not user["medico_verificado"]:
        flash("Seu registro profissional precisa ser validado antes de agendar consultas.", "error")
        return redirect(url_for("inicio_medico"))
    patient_id = request.form.get("paciente_id", type=int)
    if not patient_id or not can_access_patient(patient_id, user):
        abort(403)
    data_hora = parse_datetime_local(request.form.get("data_hora"))
    local = request.form.get("local", "").strip()[:180] or None
    motivo = request.form.get("motivo", "").strip()[:500] or None
    if not data_hora:
        flash("Informe a data e o horário da consulta.", "error")
        return redirect(url_for("inicio_medico", paciente_id=patient_id))
    with db_session() as (_, cursor):
        cursor.execute(
            "INSERT INTO consultas (paciente_id, medico_id, data_hora, local, motivo) "
            "VALUES (%s, %s, %s, %s, %s)",
            (patient_id, user["id"], data_hora, local, motivo),
        )
        consultation_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO auditoria (usuario_id, acao, recurso, recurso_id, detalhes) "
            "VALUES (%s, 'criar_consulta', 'consulta', %s, %s)",
            (user["id"], consultation_id, f"Consulta para paciente {patient_id}"),
        )
    flash("Consulta adicionada à agenda do paciente.", "success")
    return redirect(url_for("inicio_medico", paciente_id=patient_id))


@app.route("/vinculos/<int:link_id>/revogar", methods=["POST"])
@role_required("paciente")
def revogar_vinculo(link_id):
    with db_session() as (_, cursor):
        cursor.execute(
            "UPDATE vinculos_cuidado SET status = 'revogado', atualizado_em = NOW() "
            "WHERE id = %s AND paciente_id = %s AND status = 'ativo'",
            (link_id, session["user_id"]),
        )
        changed = cursor.rowcount
    if changed:
        log_audit(session["user_id"], "revogar", "vinculo", link_id)
        flash("Acesso revogado. A pessoa não poderá mais consultar seus dados pelo GlicoCheck.", "success")
    else:
        flash("Não foi possível localizar um vínculo ativo para revogar.", "error")
    return redirect(url_for("inicio_paciente"))


@app.route("/relatorios/<int:patient_id>.pdf")
@login_required
def gerar_relatorio_pdf(patient_id):
    user = current_user()
    if not can_access_patient(patient_id, user):
        abort(403)
    patient = get_patient_record(patient_id)
    if not patient:
        abort(404)
    with db_session() as (_, cursor):
        cursor.execute(
            "SELECT valor, unidade, contexto, medido_em, observacoes "
            "FROM medicoes_glicemia WHERE paciente_id = %s AND status = 'ativo' "
            "AND medido_em >= %s ORDER BY medido_em DESC",
            (patient_id, datetime.now() - timedelta(days=90)),
        )
        measurements = cursor.fetchall()
        cursor.execute(
            "SELECT titulo, orientacoes, metas, atualizado_em FROM planos_cuidado "
            "WHERE paciente_id = %s AND ativo = 1 ORDER BY atualizado_em DESC LIMIT 1",
            (patient_id,),
        )
        plan = cursor.fetchone()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=17 * mm, bottomMargin=17 * mm,
        title=f"Relatório GlicoCheck - {patient['nome']}"
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="GC_Title", parent=styles["Title"], textColor=colors.HexColor("#a10f06"), alignment=TA_LEFT, fontName="Helvetica-Bold", fontSize=19, spaceAfter=4))
    styles.add(ParagraphStyle(name="GC_Body", parent=styles["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#333333")))
    story = [
        Paragraph("GlicoCheck", styles["GC_Title"]),
        Paragraph("Resumo de acompanhamento para consulta · últimos 90 dias", styles["GC_Body"]),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>Paciente:</b> {html_escape(patient['nome'])}", styles["GC_Body"]),
        Paragraph(f"<b>Relatório gerado em:</b> {datetime.now().strftime('%d/%m/%Y às %H:%M')}", styles["GC_Body"]),
        Spacer(1, 5 * mm),
    ]
    if measurements:
        values = [float(item["valor"]) for item in measurements]
        story.append(Paragraph("<b>Resumo dos registros disponíveis</b>", styles["Heading2"]))
        summary = [
            ["Registros", "Menor registro", "Maior registro", "Média aritmética"],
            [str(len(values)), f"{min(values):.1f} mg/dL", f"{max(values):.1f} mg/dL", f"{sum(values)/len(values):.1f} mg/dL"],
        ]
        table = Table(summary, colWidths=[35 * mm, 42 * mm, 42 * mm, 48 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5eeee")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b2520")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e6dddd")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([table, Spacer(1, 5 * mm)])
        story.append(Paragraph("<b>Histórico de medições</b>", styles["Heading2"]))
        rows = [["Data e hora", "Valor", "Contexto", "Observações"]]
        for item in measurements[:100]:
            obs = (item["observacoes"] or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            rows.append([
                item["medido_em"].strftime("%d/%m/%Y %H:%M"),
                f"{float(item['valor']):.1f} {item['unidade']}",
                item["contexto"].replace("_", " ").title(),
                Paragraph(obs or "—", styles["GC_Body"]),
            ])
        history = Table(rows, colWidths=[33 * mm, 30 * mm, 36 * mm, 68 * mm], repeatRows=1)
        history.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#a10f06")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e6e6e6")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(history)
    else:
        story.append(Paragraph("Não há medições registradas nos últimos 90 dias.", styles["GC_Body"]))
    story.append(Spacer(1, 6 * mm))
    if plan:
        orient = (plan["orientacoes"] or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.extend([
            Paragraph("<b>Plano de cuidado ativo</b>", styles["Heading2"]),
            Paragraph(f"<b>{html_escape(plan['titulo'])}</b>", styles["GC_Body"]),
            Paragraph(orient, styles["GC_Body"]),
        ])
        if plan.get("metas"):
            metas = html_escape(plan["metas"]).replace("\n", "<br/>")
            story.append(Paragraph(f"<b>Metas e observações:</b><br/>{metas}", styles["GC_Body"]))
    story.extend([
        Spacer(1, 7 * mm),
        Paragraph("Este documento organiza os registros disponíveis e não constitui diagnóstico, interpretação clínica ou recomendação de tratamento. A avaliação deve ser realizada pelo profissional responsável.", styles["Italic"]),
    ])
    document.build(story)
    buffer.seek(0)
    log_audit(user["id"], "exportar", "relatorio_pdf", patient_id, "Relatório de acompanhamento de 90 dias")
    filename = f"glicocheck_relatorio_paciente_{patient_id}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.route("/minha-conta")
@login_required
def minha_conta():
    user = current_user()
    return render_template("minha_conta.html", user=user)


@app.cli.command("verificar-medico")
@click.argument("email")
def verificar_medico(email):
    """Marca como verificada uma conta médica após conferência manual do registro."""
    normalized = email.strip().lower()
    with db_session() as (_, cursor):
        cursor.execute(
            "UPDATE usuarios SET medico_verificado = 1 "
            "WHERE email = %s AND perfil = 'medico'",
            (normalized,),
        )
        changed = cursor.rowcount
    click.echo("Conta médica verificada." if changed else "Nenhuma conta médica encontrada com esse e-mail.")


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", port=int(os.getenv("PORT", "5000")))
