from flask import Flask, render_template, request, redirect
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)

def conectar():
    return mysql.connector.connect(**DB_CONFIG)

# ---------------------------------------------------------
# ROTA PRINCIPAL (INDEX)
# ---------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# ---------------------------------------------------------
# 1. PACIENTES
# ---------------------------------------------------------
@app.route("/pacientes")
def listar_pacientes():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id_paciente, nome, data_nascimento, telefone, email FROM paciente")
        pacientes = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("pacientes.html", pacientes=pacientes)
    except Exception as erro:
        return f"Erro ao listar pacientes: {erro}"

@app.route("/pacientes/novo")
def formulario_paciente():
    return render_template("paciente_form.html")

@app.route("/pacientes/cadastrar", methods=["POST"])
def cadastrar_paciente():
    try:
        nome = request.form["nome"]
        data_nascimento = request.form["data_nascimento"]
        telefone = request.form["telefone"]
        email = request.form["email"]
        senha = request.form["senha"]

        conexao = conectar()
        cursor = conexao.cursor()
        sql = "INSERT INTO paciente (nome, data_nascimento, telefone, email, senha) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (nome, data_nascimento, telefone, email, senha))
        conexao.commit()
        cursor.close()
        conexao.close()

        return redirect("/pacientes")
    except Exception as erro:
        return f"Erro ao cadastrar paciente: {erro}"

# ---------------------------------------------------------
# 2. CUIDADORES
# ---------------------------------------------------------
@app.route("/cuidadores")
def listar_cuidadores():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id_cuidador, nome, telefone, email FROM cuidador")
        cuidadores = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("cuidadores.html", cuidadores=cuidadores)
    except Exception as erro:
        return f"Erro ao listar cuidadores: {erro}"

# ---------------------------------------------------------
# 3. MEDIÇÕES
# ---------------------------------------------------------
@app.route("/medicoes")
def listar_medicoes():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id_medicao, id_paciente, tipo_medicao, valor, data_hora, observacao FROM medicao")
        medicoes = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("medicoes.html", medicoes=medicoes)
    except Exception as erro:
        return f"Erro ao listar medições: {erro}"

# ---------------------------------------------------------
# 4. MEDICAMENTOS
# ---------------------------------------------------------
@app.route("/medicamentos")
def listar_medicamentos():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id_medicamento, id_paciente, nome_medicamento, informacao_uso, data_inicio, observacoes FROM medicamento")
        medicamentos = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("medicamentos.html", medicamentos=medicamentos)
    except Exception as erro:
        return f"Erro ao listar medicamentos: {erro}"

# ---------------------------------------------------------
# 5. COMPROMISSOS
# ---------------------------------------------------------
@app.route("/compromissos")
def listar_compromissos():
    try:
        conexao = conectar()
        cursor = conexao.cursor(dictionary=True)
        cursor.execute("SELECT id_compromisso, id_paciente, tipo_compromisso, data_hora, observacao FROM compromisso")
        compromissos = cursor.fetchall()
        cursor.close()
        conexao.close()
        return render_template("compromissos.html", compromissos=compromissos)
    except Exception as erro:
        return f"Erro ao listar compromissos: {erro}"

if __name__ == "__main__":
    app.run(debug=True)