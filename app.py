import streamlit as st
import json
import pandas as pd
from datetime import datetime
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import base64
import requests
import pytz
import bcrypt
import hashlib
import subprocess

# Carrega variáveis do .env
load_dotenv()

# --- Definição do Fuso Horário ---
FUSO_HORARIO_BRASIL = pytz.timezone('America/Sao_Paulo')

LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'
USUARIOS_FILE = 'usuarios.json'

EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# --- Sessão ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.user_role = None
    st.session_state.senha_inicial_pendente = False


def salvar_com_commit_json(arquivo, dados, mensagem_commit):
    """Salva dados em um arquivo JSON e faz um commit e push para o GitHub."""
    try:
        # 1. Salva o arquivo localmente no container do Streamlit Cloud
        with open(arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=4)
        print(f"DEBUG: Arquivo {arquivo} salvo localmente. Mensagem: {mensagem_commit}")

        # 2. Configura as credenciais do Git usando o token do ambiente
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            st.error("Erro: GITHUB_TOKEN não configurado como secret no Streamlit Cloud. Não foi possível fazer o commit para o GitHub.")
            print("DEBUG: GITHUB_TOKEN não encontrado nas variáveis de ambiente.")
            return

        # Configura o git com um usuário genérico para o bot do Streamlit
        subprocess.run(["git", "config", "user.name", "Streamlit Cloud Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "streamlit-bot@example.com"], check=True)

        # 3. Adiciona o arquivo às mudanças do Git
        # Usar --ignore-errors para que não falhe se o arquivo não estiver presente ou rastreado
        subprocess.run(["git", "add", arquivo], check=False) 
        print(f"DEBUG: {arquivo} adicionado ao staging do Git.")

        # 4. Verifica se há algo para commitar antes de tentar commitar
        # git diff-index --quiet HEAD -- (Verifica se há mudanças no diretório de trabalho em relação ao HEAD)
        # Se houver diferenças, o comando retorna código 1. Se não houver, retorna 0.
        try:
            subprocess.run(["git", "diff-index", "--quiet", "HEAD", "--"], check=True)
            print("DEBUG: Nenhuma alteração para commitar. Ignorando commit e push.")
            return # Não há alterações, então não precisa commitar nem fazer push
        except subprocess.CalledProcessError:
            # Há alterações, continue para commit
            pass

        # 5. Faz o commit
        subprocess.run(["git", "commit", "-m", mensagem_commit], check=True)
        print(f"DEBUG: Commit realizado com a mensagem: '{mensagem_commit}'.")

        # 6. Faz o push para o repositório remoto
        # A URL do repositório é modificada para incluir o token para autenticação via HTTPS.
        # Isso é necessário porque o ambiente do Streamlit não mantém credenciais git automaticamente.
        
        # Obtém a URL remota atual
        current_repo_url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
        
        # Converte para URL HTTPS com o token para autenticação
        # Ex: de 'git@github.com:usuario/repo.git' ou 'https://github.com/usuario/repo.git'
        # para 'https://oauth2:YOUR_TOKEN@github.com/usuario/repo.git'
        if current_repo_url.startswith("git@"):
            repo_path = current_repo_url.split("git@github.com:")[1]
            push_url = f"https://oauth2:{github_token}@github.com/{repo_path}"
        elif current_repo_url.startswith("https://"):
            # Substitui qualquer credencial existente na URL HTTPS ou adiciona se não houver
            parts = current_repo_url.split("//")
            # Remove credenciais existentes antes de adicionar as novas
            host_and_path = parts[1].split("@")[-1] 
            push_url = f"{parts[0]}//oauth2:{github_token}@{host_and_path}"
        else:
            st.error(f"Erro: Formato de URL de repositório desconhecido: {current_repo_url}. Não é possível fazer o push com o token.")
            print(f"DEBUG: Formato de URL de repositório desconhecido: {current_repo_url}")
            return
            
        subprocess.run(["git", "push", push_url], check=True)
        print(f"DEBUG: Alterações de {arquivo} empurradas para o GitHub.")

    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip() if e.stderr else e.output.strip()
        st.error(f"Erro no Git ao salvar {arquivo}: {error_output}. Verifique as permissões do seu GITHUB_TOKEN.")
        print(f"DEBUG: Erro do subprocesso Git: {error_output}")
    except Exception as e:
        st.error(f"Erro inesperado ao salvar {arquivo}: {e}")
        print(f"DEBUG: Erro inesperado ao salvar arquivo: {e}")

def carregar_lembretes():
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def salvar_lembretes(lembretes, mensagem_commit="Lembretes atualizados."):
    salvar_com_commit_json(LEMBRETES_FILE, lembretes, mensagem_commit)

def carregar_configuracoes():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def salvar_configuracoes(configuracoes, mensagem_commit="Configurações atualizadas."):
    salvar_com_commit_json(CONFIG_FILE, configuracoes, mensagem_commit)

def carregar_usuarios():
    try:
        with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
            usuarios = json.load(f)
            # ADICIONADO PARA COMPATIBILIDADE RETROATIVA:
            for user in usuarios:
                if "senha_inicial_definida" not in user:
                    user["senha_inicial_definida"] = True # Usuários existentes são considerados com senha inicial definida
            return usuarios
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def salvar_usuarios(usuarios, mensagem_commit="Usuários atualizados."):
    salvar_com_commit_json(USUARIOS_FILE, usuarios, mensagem_commit)

def adicionar_usuario(username, password, role):
    usuarios = carregar_usuarios()
    if any(u['username'] == username for u in usuarios):
        return False, "Usuário já existe."

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    novo_usuario = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hashed_password,
        "role": role,
        "senha_inicial_definida": False
    }
    usuarios.append(novo_usuario)
    salvar_usuarios(usuarios, f"Adicionado novo usuário: {username}")
    return True, "Usuário adicionado com sucesso."

def editar_usuario(user_id, novo_username, nova_role=None, nova_senha=None):
    usuarios = carregar_usuarios()
    user_found = False
    for i, user in enumerate(usuarios):
        if user['id'] == user_id:
            user_found = True
            if any(u['username'] == novo_username and u['id'] != user_id for u in usuarios):
                return False, "Nome de usuário já existe."

            usuarios[i]['username'] = novo_username
            if nova_role:
                usuarios[i]['role'] = nova_role
            if nova_senha:
                hashed_new_password = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                usuarios[i]['password_hash'] = hashed_new_password
            salvar_usuarios(usuarios, f"Usuário {novo_username} editado.")
            return True, "Usuário atualizado com sucesso!"
    return False, "Usuário não encontrado."

def deletar_usuario(user_id):
    usuarios = carregar_usuarios()
    usuarios_restantes = [u for u in usuarios if u['id'] != user_id]
    if len(usuarios_restantes) < len(usuarios):
        salvar_usuarios(usuarios_restantes, f"Usuário com ID {user_id} deletado.")

        # NOVO: Remover também os lembretes do usuário
        lembretes = carregar_lembretes()
        lembretes_restantes = [l for l in lembretes if l.get('user_id') != user_id]
        salvar_lembretes(lembretes_restantes, f"Lembretes do usuário {user_id} removidos após exclusão.")

        return True, "Usuário e seus lembretes deletados com sucesso."
    return False, "Usuário não encontrado."


def enviar_email(destino, assunto, corpo, usuario_id=None):
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        st.error("Credenciais de e-mail não configuradas. Verifique as variáveis de ambiente GMAIL_USER e GMAIL_APP_PASSWORD.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE_USER
        msg['To'] = destino
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_REMETENTE_USER, EMAIL_REMETENTE_PASS)
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail para {destino}: {e}")
        return False

def get_gravatar_url(email):
    if not email:
        return "https://www.gravatar.com/avatar/?d=mp"
    email_hash = hashlib.md5(email.lower().strip().encode('utf-8')).hexdigest()
    return f"https://www.gravatar.com/avatar/{email_hash}?d=mp"


# === UI PRINCIPAL - ORDEM CORRIGIDA ===

# Bloco para Forçar Troca de Senha no Primeiro Login (PRIORITÁRIO)
if st.session_state.senha_inicial_pendente:
    st.title("Troca de Senha no Primeiro Login")
    st.warning("Por favor, defina uma nova senha para sua conta antes de continuar.")

    nova_senha = st.text_input("Nova Senha", type="password", key="nova_senha_inicial")
    confirma_senha = st.text_input("Confirme a Nova Senha", type="password", key="confirma_senha_inicial")

    if st.button("Definir Nova Senha"):
        if nova_senha and confirma_senha:
            if nova_senha == confirma_senha:
                usuarios = carregar_usuarios()
                user_index = -1
                for i, user in enumerate(usuarios):
                    if user['id'] == st.session_state.user_id:
                        user_index = i
                        break

                if user_index != -1:
                    hashed_new_password = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    usuarios[user_index]['password_hash'] = hashed_new_password
                    usuarios[user_index]['senha_inicial_definida'] = True

                    salvar_usuarios(usuarios, f"Senha inicial do usuário {st.session_state.username} alterada.")

                    st.success("Sua senha foi atualizada com sucesso! Você será redirecionado para o login.")
                    st.session_state.senha_inicial_pendente = False
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Erro: Usuário não encontrado no sistema.")
            else:
                st.error("As senhas não coincidem.")
        else:
            st.error("Por favor, preencha todos os campos de senha.")
    st.markdown("---")
    st.info("Você precisa definir uma nova senha para acessar o sistema.")

# Lógica de Login (SEGUNDO na ordem)
elif not st.session_state.logged_in:
    st.markdown("<h2 style='text-align: center;'>Bem-vindo ao Sistema de Lembretes</h2>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Faça Login para Continuar</h3>", unsafe_allow_html=True)

    login_col_spacer_left, login_col_form, login_col_spacer_right = st.columns([1,2,1])

    with login_col_form:
        with st.form("login_form"):
            username_login = st.text_input("Nome de Usuário", key="username_login_input")
            password_login = st.text_input("Senha", type="password", key="password_login_input")

            if st.form_submit_button("Entrar"):
                usuarios = carregar_usuarios()
                user_found = False
                for user in usuarios:
                    if user['username'] == username_login:
                        user_found = True
                        print(f"DEBUG: Tentando logar com '{username_login}'. Senha hash armazenada: '{user['password_hash']}'")
                        print(f"DEBUG: Senha digitada (hash check): '{password_login}'")
                        if bcrypt.checkpw(password_login.encode('utf-8'), user['password_hash'].encode('utf-8')):
                            print(f"DEBUG: bcrypt.checkpw retornou TRUE para '{username_login}'.")
                            st.session_state.username = user['username']
                            st.session_state.user_id = user['id']
                            st.session_state.user_role = user['role']

                            if not user.get("senha_inicial_definida", True):
                                print(f"DEBUG: '{username_login}' tem 'senha_inicial_definida': False. Redirecionando para troca de senha.")
                                st.session_state.senha_inicial_pendente = True
                                st.session_state.logged_in = False
                                st.rerun()
                            else:
                                print(f"DEBUG: '{username_login}' tem 'senha_inicial_definida': True. Logando normalmente.")
                                st.session_state.senha_inicial_pendente = False
                                st.session_state.logged_in = True
                                st.rerun()
                            break

                if not user_found:
                    st.error("Nome de usuário não encontrado.")
                elif not st.session_state.logged_in and not st.session_state.senha_inicial_pendente:
                    print(f"DEBUG: Senha incorreta para o usuário '{username_login}'.")
                    st.error("Senha incorreta.")

# Lógica de interface principal após login bem-sucedido (ÚLTIMO na ordem)
elif st.session_state.logged_in:
    st.sidebar.markdown(f"**Bem-vindo, {st.session_state.username}!**")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_id = None
        st.session_state.user_role = None
        st.session_state.senha_inicial_pendente = False
        st.rerun()

    st.title("Sistema de Lembretes")

    tabs = ["Meus Lembretes"]
    if st.session_state.user_role == 'admin':
        tabs.append("Administração")
    tabs.append("Configurações de E-mail")

    selected_tab = st.sidebar.radio("Navegação", tabs)


    if selected_tab == "Meus Lembretes":
        st.subheader("Adicionar Novo Lembrete")
        with st.form("novo_lembrete_form", clear_on_submit=True):
            titulo = st.text_input("Título do Lembrete")
            descricao = st.text_area("Descrição")
            data = st.date_input("Data", min_value=datetime.now(FUSO_HORARIO_BRASIL).date())
            hora = st.time_input("Hora", value=datetime.now(FUSO_HORARIO_BRASIL).time())
            submit_button = st.form_submit_button("Salvar Lembrete")

            if submit_button:
                if titulo and descricao and data and hora:
                    lembretes = carregar_lembretes()
                    novo_lembrete = {
                        "id": str(uuid.uuid4()),
                        "user_id": st.session_state.user_id,
                        "titulo": titulo,
                        "descricao": descricao,
                        "data": data.strftime('%Y-%m-%d'),
                        "hora": hora.strftime('%H:%M'),
                        "enviado": False
                    }
                    lembretes.append(novo_lembrete)
                    salvar_lembretes(lembretes, f"Novo lembrete '{titulo}' adicionado por {st.session_state.username}.")
                    st.success("Lembrete salvo com sucesso!")
                    st.rerun()

        st.subheader("Meus Lembretes Pendentes")
        lembretes = carregar_lembretes()

        meus_lembretes = [l for l in lembretes if l.get('user_id') == st.session_state.user_id]

        if meus_lembretes:
            for lembrete in meus_lembretes:
                lembrete.setdefault('enviado', False)

            df = pd.DataFrame(meus_lembretes)
            # CORREÇÃO AQUI: Localiza o fuso horário da coluna 'Data e Hora'
            df["Data e Hora"] = pd.to_datetime(df["data"] + " " + df["hora"], errors='coerce').dt.tz_localize(FUSO_HORARIO_BRASIL)

            agora = datetime.now(FUSO_HORARIO_BRASIL).replace(second=0, microsecond=0)

            df_pendentes = df[
                (df["Data e Hora"] > agora) &
                (df["enviado"] == False)
            ].sort_values("Data e Hora")

            if not df_pendentes.empty:
                st.write("Lembretes agendados e pendentes de envio:")
                df_pendentes["Data e Hora"] = df_pendentes["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')

                st.dataframe(
                    df_pendentes[['titulo', 'descricao', 'Data e Hora']],
                    hide_index=True,
                    use_container_width=True
                )

                st.subheader("Deletar Lembretes")
                lembretes_para_deletar = st.multiselect(
                    "Selecione o(s) lembrete(s) para deletar:",
                    options=df_pendentes['titulo'].tolist()
                )
                if st.button("Confirmar Deleção"):
                    if lembretes_para_deletar:
                        lembretes_atuais = carregar_lembretes()
                        lembretes_restantes = [
                            l for l in lembretes_atuais
                            if not (l.get('user_id') == st.session_state.user_id and l['titulo'] in lembretes_para_deletar)
                        ]
                        if len(lembretes_restantes) < len(lembretes_atuais):
                            salvar_lembretes(lembretes_restantes, f"Lembretes deletados por {st.session_state.username}.")
                            st.success("Lembrete(s) deletado(s) com sucesso!")
                            st.rerun()
                        else:
                            st.warning("Nenhum lembrete selecionado para deletar foi encontrado.")
                    else:
                        st.info("Nenhum lembrete selecionado para deletar.")
            else:
                st.info("Nenhum lembrete futuro e pendente de envio encontrado.")

            st.subheader("Lembretes Já Enviados ou Passados")
            df_passados_ou_enviados = df[
                (df["Data e Hora"] <= agora) |
                (df["enviado"] == True)
            ].sort_values("Data e Hora", ascending=False)

            if not df_passados_ou_enviados.empty:
                df_passados_ou_enviados["Data e Hora"] = df_passados_ou_enviados["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')
                df_passados_ou_enviados["Enviado"] = df_passados_ou_enviados["enviado"].apply(lambda x: "✅ Sim" if x else "❌ Não")
                st.dataframe(
                    df_passados_ou_enviados[['titulo', 'descricao', 'Data e Hora', 'Enviado']],
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("Nenhum lembrete enviado ou passado encontrado.")
        else:
            st.info("Você não tem lembretes cadastrados.")

    elif selected_tab == "Configurações de E-mail":
        st.subheader("Configurações de E-mail para Lembretes")
        configuracoes = carregar_configuracoes()

        user_config = configuracoes.get(st.session_state.user_id, {})
        email_destino_atual = user_config.get("email_destino", "")

        novo_email_destino = st.text_input("Seu E-mail de Destino para Lembretes", value=email_destino_atual)

        if st.button("Salvar E-mail de Destino"):
            if novo_email_destino:
                configuracoes[st.session_state.user_id] = {"email_destino": novo_email_destino}
                salvar_configuracoes(configuracoes, f"E-mail de destino atualizado para {st.session_state.username}.")
                st.success(f"E-mail de destino salvo como: {novo_email_destino}")
            else:
                st.error("Por favor, insira um e-mail de destino válido.")

    elif selected_tab == "Administração" and st.session_state.user_role == 'admin':
        admin_tab1, admin_tab2 = st.tabs(["Gerenciar Usuários", "Todos os Lembretes"])

        with admin_tab1:
            st.subheader("Gerenciar Usuários")
            usuarios = carregar_usuarios()

            st.write("### Lista de Usuários")
            if usuarios:
                df_users = pd.DataFrame(usuarios)
                df_display_users = df_users[['username', 'role', 'id', 'senha_inicial_definida']]
                df_display_users.columns = ['Nome de Usuário', 'Nível de Acesso', 'ID', 'Senha Inicial Definida']

                st.dataframe(df_display_users, hide_index=True, use_container_width=True)

                st.markdown("---")
                st.write("### Adicionar Novo Usuário")
                with st.form("add_user_form", clear_on_submit=True):
                    new_username = st.text_input("Nome de Usuário (Novo)")
                    new_password = st.text_input("Senha (Novo)", type="password")
                    confirm_new_password = st.text_input("Confirme a Senha (Novo)", type="password")
                    new_role = st.selectbox("Nível de Acesso", ["normal", "admin"])
                    add_user_button = st.form_submit_button("Adicionar Usuário")

                    if add_user_button:
                        if new_username and new_password and confirm_new_password:
                            if new_password == confirm_new_password:
                                sucesso, mensagem = adicionar_usuario(new_username, new_password, new_role)
                                if sucesso:
                                    st.success(f"{mensagem} O usuário precisará trocar a senha no primeiro login.")
                                    st.rerun()
                                else:
                                    st.error(mensagem)
                            else:
                                st.error("As senhas não coincidem.")
                        else:
                            st.error("Por favor, preencha todos os campos para adicionar o usuário.")

                st.markdown("---")
                st.write("### Editar/Deletar Usuário Existente")
                user_options = {u['username']: u['id'] for u in usuarios}
                selected_username = st.selectbox("Selecione um usuário:", options=list(user_options.keys()) if user_options else ["Nenhum usuário"])

                if selected_username and selected_username != "Nenhum usuário":
                    selected_user_id = user_options[selected_username]
                    user_to_edit = next(u for u in usuarios if u['id'] == selected_user_id)

                    with st.form(key=f"edit_user_form_{selected_user_id}"):
                        st.write(f"Editando usuário: **{selected_user_id}**")
                        novo_username = st.text_input("Novo Nome de Usuário", value=user_to_edit['username'], key=f"edit_username_{selected_user_id}")
                        nova_role = st.selectbox("Novo Nível de Acesso", ["admin", "normal"], index=["admin", "normal"].index(user_to_edit['role']), key=f"edit_role_{selected_user_id}")
                        nova_senha = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key=f"edit_password_{selected_user_id}")

                        col_edit_del_user_form = st.columns(2)
                        with col_edit_del_user_form[0]:
                            submit_edit_user = st.form_submit_button("Salvar Alterações")
                        with col_edit_del_user_form[1]:
                            if st.form_submit_button("Deletar Usuário", type="secondary"):
                                st.session_state[f"confirm_delete_user_{selected_user_id}"] = True
                                st.rerun()

                        if submit_edit_user:
                            if nova_senha:
                                sucesso, mensagem = editar_usuario(selected_user_id, novo_username, nova_role, nova_senha)
                            else:
                                sucesso, mensagem = editar_usuario(selected_user_id, novo_username, nova_role)

                            if sucesso:
                                st.success(mensagem)
                                st.rerun()
                            else:
                                st.error(mensagem)

                    if st.session_state.get(f"confirm_delete_user_{selected_user_id}", False):
                        st.warning(f"Tem certeza que deseja deletar o usuário {selected_username}? Esta ação é irreversível.")
                        col_confirm_del = st.columns(2)
                        with col_confirm_del[0]:
                            if st.button(f"Confirmar Deleção de {selected_username}", key=f"final_confirm_del_{selected_user_id}"):
                                sucesso, mensagem = deletar_usuario(selected_user_id)
                                if sucesso:
                                    st.success(mensagem)
                                    st.session_state[f"confirm_delete_user_{selected_user_id}"] = False
                                    st.rerun()
                                else:
                                    st.error(mensagem)
                        with col_confirm_del[1]:
                            if st.button("Cancelar Deleção", key=f"cancel_del_{selected_user_id}"):
                                st.session_state[f"confirm_delete_user_{selected_user_id}"] = False
                                st.rerun()
                else:
                    st.info("Nenhum usuário selecionado ou cadastrado para editar/deletar.")


        with admin_tab2:
            st.subheader("Todos os Lembretes do Sistema")
            try:
                with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
                    all_lembretes = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                all_lembretes = []

            for lembrete in all_lembretes:
                lembrete.setdefault('user_id', None)

            if all_lembretes:
                df_all = pd.DataFrame(all_lembretes)
                df_all["Data e Hora"] = pd.to_datetime(df_all["data"] + " " + df_all["hora"], errors='coerce')
                df_all = df_all.dropna(subset=["Data e Hora"]).sort_values("Data e Hora")
                df_all["Enviado"] = df_all["enviado"].apply(lambda x: "✅ Sim" if x else "❌ Não")
                df_all["Data e Hora"] = df_all["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')

                all_users = carregar_usuarios()
                user_map = {u['id']: u['username'] for u in all_users}
                df_all['Usuário'] = df_all['user_id'].map(user_map).fillna('Desconhecido')
                st.dataframe(
                    df_all[['Usuário', 'titulo', 'descricao', 'Data e Hora', 'Enviado']],
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("Nenhum lembrete cadastrado no sistema.")