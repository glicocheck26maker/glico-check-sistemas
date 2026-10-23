from flask import Flask, render_template, request, redirect, session, url_for
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)
app.secret_key = "glicocheck_chave_secreta_segura"

# Configurações para atualização imediata de arquivos estáticos
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

def conectar():
    return mysql.connector.connect(**DB_CONFIG)

# ---------------------------------------------------------
# CONTROLE DE NAVEGAÇÃO E DASHBOARDS DINÂMICOS
# ---------------------------------------------------------
@app.route("/")
def raiz():
    if session.get("usuario_logado"):
        return redirect("/inicio")
    return redirect("/cadastro")

@app.route("/inicio")
def index():
    if not session.get("usuario_logado"):
        return redirect("/cadastro")
        
    user_id = session.get("id_usuario")
    perfil = session.get("perfil", "paciente").lower()

    conexao = conectar()
    cursor = conexao.cursor(dictionary=True)

    if perfil == "medico":
        # Busca pacientes vinculados ao médico logado
        query_pacientes = """
            SELECT u.id, u.nome, u.email, u.telefone 
            FROM usuario u
            JOIN medico_paciente mp ON u.id = mp.id_paciente
            WHERE mp.id_medico = %s
        """
        cursor.execute(query_pacientes, (user_id,))
        pacientes_vinculados = cursor.fetchall()

        # Todos os pacientes do sistema para a lista de vinculação
        cursor.execute("SELECT id, nome, email FROM usuario WHERE perfil = 'paciente'")
        todos_pacientes = cursor.fetchall()

        cursor.close()
        conexao.close()
        return render_template("dashboard_medico.html", pacientes=pacientes_vinculados, todos_pacientes=todos_pacientes)

    elif perfil == "cuidador":
        # Busca pacientes vinculados ao cuidador logado
        query_pacientes = """
            SELECT u.id, u.nome, u.email, u.telefone 
            FROM usuario u
            JOIN cuidador_paciente cp ON u.id = cp.id_paciente
            WHERE cp.id_cuidador = %s
        """
        cursor.execute(query_pacientes, (user_id,))
        pacientes_vinculados = cursor.fetchall()

        # Todos os pacientes para seleção
        cursor.execute("SELECT id, nome, email FROM usuario WHERE perfil = 'paciente'")
        todos_pacientes = cursor.fetchall()

        cursor.close()
        conexao.close()
        return render_template("dashboard_cuidador.html", pacientes=pacientes_vinculados, todos_pacientes=todos_pacientes)

    elif perfil == "paciente":
        # Cuidadores vinculados ao paciente
        query_cuidadores = """
            SELECT u.id, u.nome, u.email, u.telefone 
            FROM usuario u
            JOIN cuidador_paciente cp ON u.id = cp.id_cuidador
            WHERE cp.id_paciente = %s
        """
        cursor.execute(query_cuidadores, (user_id,))
        cuidadores_vinculados = cursor.fetchall()

        # Médicos vinculados ao paciente
        query_medicos = """
            SELECT u.id, u.nome, u.email, u.telefone 
            FROM usuario u
            JOIN medico_paciente mp ON u.id = mp.id_medico
            WHERE mp.id_paciente = %s
        """
        cursor.execute(query_medicos, (user_id,))
        medicos_vinculados = cursor.fetchall()

        # Todos os cuidadores para modal de vínculo
        cursor.execute("SELECT id, nome, email FROM usuario WHERE perfil = 'cuidador'")
        todos_cuidadores = cursor.fetchall()

        cursor.close()
        conexao.close()
        return render_template("dashboard_paciente.html", cuidadores=cuidadores_vinculados, medicos=medicos_vinculados, todos_cuidadores=todos_cuidadores)

    conexao.close()
    return render_template("landing.html")

# ---------------------------------------------------------
# CADASTRO, LOGIN E LOGOUT
# ---------------------------------------------------------
@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        data_nascimento = request.form.get('data_nascimento')
        telefone = request.form.get('telefone')
        email = request.form.get('email')
        senha = request.form.get('senha')
        confirmar_senha = request.form.get('confirmar_senha')
        perfil = request.form.get('perfil')

        if len(senha) < 8:
            return render_template('cadastro.html', erro='A senha deve conter no mínimo 8 caracteres.')

        if senha != confirmar_senha:
            return render_template('cadastro.html', erro='As senhas digitadas não conferem.')

        try:
            conexao = conectar()
            cursor = conexao.cursor()

            query = """
                INSERT INTO usuario (nome, data_nascimento, telefone, email, senha, perfil, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Ativo')
            """
            cursor.execute(query, (nome, data_nascimento, telefone, email, senha, perfil))
            conexao.commit()
            
            id_usuario = cursor.lastrowid
            cursor.close()
            conexao.close()

            session['id_usuario'] = id_usuario
            session['usuario_logado'] = True
            session['nome_usuario'] = nome
            session['perfil'] = perfil.lower()

            return redirect(url_for('index'))

        except mysql.connector.Error as err:
            if err.errno == 1062:
                return render_template('cadastro.html', erro='Este e-mail já está cadastrado na plataforma.')
            return render_template('cadastro.html', erro=f"Erro no banco de dados: {err}")

    return render_template('cadastro.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        email = request.form.get("email") or request.form.get("usuario")
        senha = request.form.get("senha")
        
        try:
            conexao = conectar()
            cursor = conexao.cursor(dictionary=True)
            
            sql = "SELECT id, nome, perfil FROM usuario WHERE email = %s AND senha = %s AND status = 'Ativo'"
            cursor.execute(sql, (email, senha))
            usuario = cursor.fetchone()
            
            cursor.close()
            conexao.close()

            if usuario:
                session["id_usuario"] = usuario["id"]
                session["usuario_logado"] = True
                session["nome_usuario"] = usuario["nome"]
                session["perfil"] = usuario["perfil"].lower() 
                return redirect("/inicio")
            else:
                erro = "E-mail ou senha incorretos."
        except Exception as e:
            erro = f"Erro na conexão com o banco de dados: {e}"

    return render_template("login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/cadastro")

# ---------------------------------------------------------
# ROTAS DE VINCULAÇÃO DINÂMICA (N:M)
# ---------------------------------------------------------
@app.route('/vincular-paciente-medico', methods=['POST'])
def vincular_paciente_medico():
    if session.get('perfil') == 'medico':
        medico_id = session.get('id_usuario')
        paciente_id = request.form.get('id_paciente')

        try:
            conexao = conectar()
            cursor = conexao.cursor()
            cursor.execute("INSERT IGNORE INTO medico_paciente (id_medico, id_paciente) VALUES (%s, %s)", (medico_id, paciente_id))
            conexao.commit()
            cursor.close()
            conexao.close()
        except Exception:
            pass

    return redirect(url_for('index'))

@app.route('/vincular-cuidador-paciente', methods=['POST'])
def vincular_cuidador_paciente():
    if session.get('perfil') in ['paciente', 'cuidador']:
        if session.get('perfil') == 'paciente':
            paciente_id = session.get('id_usuario')
            cuidador_id = request.form.get('id_cuidador')
        else:
            cuidador_id = session.get('id_usuario')
            paciente_id = request.form.get('id_paciente')

        try:
            conexao = conectar()
            cursor = conexao.cursor()
            cursor.execute("INSERT IGNORE INTO cuidador_paciente (id_cuidador, id_paciente) VALUES (%s, %s)", (cuidador_id, paciente_id))
            conexao.commit()
            cursor.close()
            conexao.close()
        except Exception:
            pass

    return redirect(url_for('index'))

# ---------------------------------------------------------
# MÓDULOS DE LISTAGEM
# ---------------------------------------------------------
@app.route("/pacientes")
def listar_pacientes():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id, nome, data_nascimento, telefone, email FROM usuario WHERE perfil = 'paciente'")
        pacientes = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("pacientes.html", pacientes=pacientes)
    except Exception as erro:
        return f"Erro ao listar pacientes: {erro}"

@app.route("/cuidadores")
def listar_cuidadores():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id, nome, telefone, email FROM usuario WHERE perfil = 'cuidador'")
        cuidadores = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("cuidadores.html", cuidadores=cuidadores)
    except Exception as erro:
        return f"Erro ao listar cuidadores: {erro}"

@app.route("/medicoes")
def listar_medicoes():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        sql = """
            SELECT m.id_medicao, m.tipo_medicao, m.valor, m.data_hora, m.observacao, u.nome AS paciente_nome
            FROM medicao m
            LEFT JOIN usuario u ON m.id_paciente = u.id
            ORDER BY m.data_hora DESC
        """
        cursor.execute(sql)
        medicoes = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("medicoes.html", medicoes=medicoes)
    except Exception as erro:
        return f"Erro ao listar medições: {erro}"

@app.route("/medicamentos")
def listar_medicamentos():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        sql = """
            SELECT m.id_medicamento, m.nome_medicamento, m.informacao_uso, m.data_inicio, m.observacoes, u.nome AS paciente_nome
            FROM medicamento m
            LEFT JOIN usuario u ON m.id_paciente = u.id
        """
        cursor.execute(sql)
        medicamentos = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("medicamentos.html", medicamentos=medicamentos)
    except Exception as erro:
        return f"Erro ao listar medicamentos: {erro}"

@app.route("/compromissos")
def listar_compromissos():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        sql = """
            SELECT c.id_compromisso, c.tipo_compromisso, c.data_hora, c.observacao, u.nome AS paciente_nome
            FROM compromisso c
            LEFT JOIN usuario u ON c.id_paciente = u.id
            ORDER BY c.data_hora ASC
        """
        cursor.execute(sql)
        compromissos = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("compromissos.html", compromissos=compromissos)
    except Exception as erro:
        return f"Erro ao listar compromissos: {erro}"

if __name__ == "__main__":
    app.run(debug=True)