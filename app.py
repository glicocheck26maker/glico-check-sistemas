from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'glicocheck_chave_secreta'

# 1. Rota da Landing Page
@app.route('/')
def landing():
    return render_template('landing.html')

# 2. Rota de Login (Única e corrigida)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '')
        perfil = request.form.get('perfil', 'cuidador').strip().lower()
        
        session['nome'] = email.split('@')[0] if email else 'Usuário'
        session['perfil'] = perfil
        
        # Redirecionamento blindado de acordo com a escolha no select
        if perfil == 'paciente':
            return redirect(url_for('inicio_paciente'))
        elif perfil == 'medico':
            return redirect(url_for('inicio_medico'))
        else:
            return redirect(url_for('inicio_cuidador'))
            
    return render_template('login.html')

# 3. Rota de Cadastro
@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome')
        perfil = request.form.get('perfil', 'cuidador')
        session['nome'] = nome if nome else 'Novo Usuário'
        
        if perfil == 'paciente':
            return redirect(url_for('inicio_paciente'))
        elif perfil == 'medico':
            return redirect(url_for('inicio_medico'))
        else:
            return redirect(url_for('inicio_cuidador'))
            
    return render_template('cadastro.html')

# Rotas dos Painéis
@app.route('/inicio-cuidador')
def inicio_cuidador():
    return render_template('dashboard_cuidador.html')

@app.route('/inicio-paciente')
def inicio_paciente():
    return render_template('dashboard_paciente.html')

@app.route('/inicio-medico')
def inicio_medico():
    return render_template('dashboard_medico.html')

# 5. Rota de Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)