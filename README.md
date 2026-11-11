# GlicoCheck — MVP integrado

Este pacote parte do ZIP enviado e preserva a landing page, o monograma oficial, as quatro imagens do carrossel, a foto da equipe, o vídeo institucional e a folha de estilos original. A camada de autenticação e os painéis foram reconstruídos para usar dados reais do MySQL.

## O que já está implementado

- Cadastro persistente de paciente, cuidador e médico.
- Login por e-mail e senha com hash seguro. O perfil vem do banco, não de um seletor na tela de login.
- Sessões e proteção CSRF nos formulários POST.
- Painéis distintos para paciente, cuidador e médico.
- Convites de vínculo por código de uso único, com validade de 7 dias e armazenamento do hash do código.
- Registro de glicemia em mg/dL, com contexto, data, observações e autoria.
- Histórico de medições compartilhado com usuários vinculados.
- Rotina de tarefas e lembretes, com conclusão registrada.
- Plano de cuidado e agenda de consultas para médicos vinculados.
- Exportação PDF com os registros disponíveis dos últimos 90 dias.
- Verificação manual de cadastro profissional antes de o médico aceitar pacientes e criar planos/consultas.
- Linha do cuidado compartilhada com medições, tarefas, consultas e planos, identificando autor e horário.
- Revogação de vínculos pelo paciente.
- Trilha básica de auditoria para acessos aos painéis/dados, medições, convites, tarefas, planos, consultas e exportações.

## 1. Faça backup e prepare o ambiente

1. Guarde uma cópia do projeto atual antes de substituir arquivos.
2. Descompacte este pacote em uma pasta de trabalho.
3. Não copie a pasta `venv` do ZIP antigo. Ela não é necessária e não deve ser versionada.
4. Abra o terminal dentro da pasta `GlicoCheck_MVP`.

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Se o PowerShell bloquear a ativação, execute o terminal como seu usuário e use:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## 2. Configure o MySQL

O pacote usa um banco novo chamado `glicocheck_v2` para não apagar nem alterar tabelas antigas. Como o ZIP enviado não continha o schema anterior, esta versão não importa automaticamente os usuários ou registros do banco antigo. O banco legado permanece intocado; uma migração de dados poderá ser planejada depois de inspecionarmos sua estrutura real.

1. Abra o MySQL Workbench.
2. Abra o arquivo `schema.sql` deste pacote.
3. Execute o script inteiro. Ele cria `glicocheck_v2` e as tabelas necessárias.
4. Abra o arquivo `.env` e configure `DB_HOST`, `DB_PORT`, `DB_USER` e `DB_PASSWORD` com o seu usuário MySQL.
5. Mantenha `DB_NAME=glicocheck_v2`.

Exemplo de `.env`:

```env
SECRET_KEY=gere_uma_chave_aleatoria_longa
DB_HOST=localhost
DB_PORT=3306
DB_USER=seu_usuario_mysql
DB_PASSWORD=sua_senha_mysql
DB_NAME=glicocheck_v2
FLASK_DEBUG=1
PORT=5000
COOKIE_SECURE=0
```

Gere uma chave de sessão com:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado para `SECRET_KEY`. Não compartilhe o `.env`, não o envie ao GitHub e não use a chave de exemplo em produção.

### Atenção ao acesso do MySQL

O usuário configurado em `.env` precisa ter permissão para ler, criar e atualizar as tabelas de `glicocheck_v2`. Se você usar o mesmo usuário do banco antigo, confirme que ele tem privilégios nesse banco novo.

## 3. Inicie o sistema

Com o ambiente virtual ativado e o MySQL ligado:

```bash
python app.py
```

Acesse `http://127.0.0.1:5000`.

Fluxo de teste recomendado:

1. Abra a landing page e crie uma conta de **Paciente**.
2. No painel do paciente, gere um código de convite para **Cuidador(a)**.
3. Em uma janela anônima ou outro navegador, crie uma conta de **Cuidador(a)** e aceite o código.
4. Registre uma medição como cuidador e confira se ela aparece no painel do paciente.
5. Crie também uma conta de **Médico(a)**. Para testes, primeiro faça a verificação manual descrita abaixo.
6. Gere um convite de médico no painel do paciente e aceite-o pela conta médica.
7. Crie um plano de cuidado e uma consulta no painel médico. Confira se aparecem no painel do paciente/cuidador.
8. Gere o PDF e confira o histórico exportado.

## 4. Verificação manual de médicos (ambiente de desenvolvimento)

Por segurança, uma conta que se cadastra como médico começa como **não verificada**. O cadastro de CRM/registro é autodeclarado e não comprova habilitação profissional.

Depois de conferir a identidade e o registro por um processo externo, a equipe administradora pode marcar a conta como verificada. Em ambiente de desenvolvimento, execute:

```bash
flask --app app verificar-medico email@exemplo.com
```

Ou, diretamente no MySQL após a conferência:

```sql
UPDATE usuarios
SET medico_verificado = 1
WHERE email = 'email@exemplo.com' AND perfil = 'medico';
```

Não habilite contas médicas sem validação adequada em um ambiente real.

## 5. O que foi preservado e o que foi alterado

### Preservado

- `templates/landing.html` original.
- `static/css/style.css` original, incluindo a tipografia Inter e a pilha de fontes Apple-like.
- Logo/monograma SVG e PNG.
- Quatro imagens `slide-1.png` a `slide-4.png`.
- Imagem da equipe, estetoscópio e vídeo institucional.

### Substituído / adicionado

- `app.py`: rotas reais, autenticação, autorização e operações do MVP.
- `config.py` + `.env.example`: configuração por variáveis de ambiente.
- `schema.sql`: estrutura do banco novo.
- `templates/base.html`, `login.html`, `cadastro.html` e os três dashboards: interface integrada.
- `templates/dashboard_base.html`: estrutura compartilhada dos dashboards.
- `static/css/app.css`: glassmorphism, responsividade e componentes internos.
- `static/js/site.js`: carrossel da autenticação e mostrar/ocultar senha.

Os dashboards antigos foram guardados em `backups/` como referência, não como páginas ativas.

## 6. Ajustes importantes antes de publicar ou usar dados reais

Este pacote é uma base funcional de MVP para desenvolvimento e teste. Antes de colocar em produção ou registrar informações reais de saúde, ainda é necessário:

- configurar HTTPS e `COOKIE_SECURE=1`;
- definir política de privacidade, retenção e atendimento aos direitos dos titulares;
- validar formalmente a base legal e os fluxos de autorização/compartilhamento conforme LGPD;
- implementar verificação robusta de identidade e credenciais profissionais;
- testar permissões e segurança com revisão independente;
- configurar backup, monitoramento, logs protegidos e restauração;
- avaliar o enquadramento regulatório da Anvisa conforme a finalidade final do software;
- realizar avaliação clínica e de usabilidade com profissionais e usuários.

O relatório PDF resume registros e estatísticas descritivas. Não apresenta diagnóstico, classificação clínica, metas universais ou recomendação de tratamento. O profissional responsável deve interpretar os dados. As tarefas aparecem no painel como organização interna; esta versão ainda não envia notificações push, SMS, WhatsApp ou e-mail.

## 7. Problema comum de conexão

Se aparecer `Access denied`, revise usuário/senha/permissões MySQL no `.env`.

Se aparecer `Unknown database 'glicocheck_v2'`, execute `schema.sql` no Workbench e confirme `DB_NAME`.

Se aparecer `No module named ...`, confirme que o ambiente virtual está ativo e execute novamente:

```bash
pip install -r requirements.txt
```

## 8. Segurança das credenciais antigas

O ZIP original continha uma senha de banco escrita diretamente em `config.py`. Como ela estava dentro do projeto compactado (e possivelmente no histórico do GitHub), troque essa senha no MySQL e atualize as credenciais no `.env`. Apenas remover a senha do arquivo atual não remove uma credencial de commits antigos.
