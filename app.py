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

# === FUNÇÕES AUXILIARES GERAIS ===
def salvar_com_commit_json(arquivo, dados, mensagem_commit):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
    token = os.getenv("GITHUB_TOKEN")
    if token:
        commit_arquivo_json_para_github(
            repo_owner="Israel-ETE78",
            repo_name="lembrete",
            file_path=arquivo,
            commit_message=mensagem_commit,
            token=token
        )
    else:
        st.warning(f"⚠️ GITHUB_TOKEN não encontrado. Commit automático de '{arquivo}' não realizado.")

def commit_arquivo_json_para_github(repo_owner, repo_name, file_path, commit_message, token):
    with open(file_path, 'rb') as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode()
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }

    sha = None
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            sha = response.json().get("sha")
    except requests.exceptions.RequestException:
        pass

    data = {
        "message": commit_message,
        "content": encoded_content
    }
    if sha:
        data["sha"] = sha

    try:
        response = requests.put(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao enviar {file_path} para o GitHub: {e}")
        return False

# === FUNÇÕES DE LEMBRETES ===

def carregar_lembretes():
    if not os.path.exists(LEMBRETES_FILE):
        with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            todos = json.load(f)
            for lembrete in todos:
                lembrete.setdefault('user_id', None)

            if st.session_state.logged_in and st.session_state.user_role == 'admin':
                return todos
            elif st.session_state.logged_in:
                return [l for l in todos if l.get('user_id') == st.session_state.user_id]
            else:
                return []
    except json.JSONDecodeError:
        return []

def salvar_lembretes(lembretes):
    salvar_com_commit_json(LEMBRETES_FILE, lembretes, "🔄 Atualização automática dos lembretes")

def adicionar_lembrete(titulo, descricao, data, hora):
    lembretes = carregar_lembretes()
    novo = {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "descricao": descricao,
        "data": data,
        "hora": hora,
        "enviado": False,
        "user_id": st.session_state.user_id
    }
    lembretes.append(novo)
    salvar_lembretes(lembretes)
    st.success("Lembrete adicionado!")

def editar_lembrete(id, titulo, descricao, data, hora):
    lembretes = carregar_lembretes()
    for l in lembretes:
        if l['id'] == id and (st.session_state.user_role == 'admin' or l.get('user_id') == st.session_state.user_id):
            l.update({
                'titulo': titulo,
                'descricao': descricao,
                'data': data,
                'hora': hora,
                'enviado': False
            })
            salvar_lembretes(lembretes)
            st.success("Lembrete atualizado!")
            return
    st.warning("Você não tem permissão ou lembrete não encontrado.")

def excluir_lembrete(id):
    lembretes = carregar_lembretes()
    novo_lista = []
    removido = False
    for l in lembretes:
        if l['id'] == id and (st.session_state.user_role == 'admin' or l.get('user_id') == st.session_state.user_id):
            removido = True
            continue
        novo_lista.append(l)
    if removido:
        salvar_lembretes(novo_lista)
        st.success("Lembrete excluído!")
    else:
        st.warning("Você não tem permissão ou lembrete não encontrado.")

# === USUÁRIOS ===

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def carregar_usuarios():
    if not os.path.exists(USUARIOS_FILE):
        admin_id = str(uuid.uuid4())
        inicial = [{
            "id": admin_id,
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "role": "admin"
        }]
        salvar_com_commit_json(USUARIOS_FILE, inicial, "🛡️ Criação inicial de usuários")
        return inicial
    try:
        with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def salvar_usuarios(usuarios):
    salvar_com_commit_json(USUARIOS_FILE, usuarios, "🔄 Atualização automática dos usuários")

def get_user_by_username(username):
    return next((u for u in carregar_usuarios() if u['username'] == username), None)

def adicionar_usuario(username, password, role):
    usuarios = carregar_usuarios()
    if any(u['username'] == username for u in usuarios):
        return False, "Nome de usuário já existe."
    novo = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "role": role
    }
    usuarios.append(novo)
    salvar_usuarios(usuarios)
    return True, "Usuário adicionado com sucesso!"

def editar_usuario(user_id, new_username, new_password, new_role):
    usuarios = carregar_usuarios()
    for u in usuarios:
        if u["id"] == user_id:
            u["username"] = new_username
            if new_password:
                u["password_hash"] = hash_password(new_password)
            u["role"] = new_role
            salvar_usuarios(usuarios)
            return True, "Usuário atualizado com sucesso!"
    return False, "Usuário não encontrado."

def excluir_usuario(user_id):
    usuarios = carregar_usuarios()
    novos = [u for u in usuarios if u["id"] != user_id]
    if len(novos) == len(usuarios):
        return False
    salvar_usuarios(novos)
    
    lembretes = carregar_lembretes()
    lembretes = [l for l in lembretes if l.get("user_id") != user_id]
    salvar_lembretes(lembretes)
    return True

# === CONFIGURAÇÃO E-MAIL POR USUÁRIO ===

def carregar_configuracoes_usuario(user_id):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get(user_id, {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_configuracoes_usuario(email_destino):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    if st.session_state.user_id:
        config[st.session_state.user_id] = {"email_destino": email_destino}
    else:
        st.error("Nenhum usuário logado para salvar as configurações de e-mail.")
        return False

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    token = os.getenv("GITHUB_TOKEN")
    if token:
        commit_arquivo_json_para_github(
            repo_owner="Israel-ETE78",
            repo_name="lembrete",
            file_path=CONFIG_FILE,
            commit_message="🔄 Atualização automática das configurações",
            token=token
        )
    else:
        st.warning("⚠️ GITHUB_TOKEN não encontrado. Commit automático não realizado.")
    return True

def get_email_por_user_id(user_id):
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get(user_id, {}).get("email_destino", EMAIL_ADMIN_FALLBACK)
    except (FileNotFoundError, json.JSONDecodeError):
        return EMAIL_ADMIN_FALLBACK

# === ENVIO DE EMAIL ===

def enviar_email(destino, assunto, corpo):
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        st.error("Erro: Credenciais de e-mail não configuradas no ambiente.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE_USER
        msg['To'] = destino
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo, 'plain'))

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(EMAIL_REMETENTE_USER, EMAIL_REMETENTE_PASS)
        text = msg.as_string()
        server.sendmail(EMAIL_REMETENTE_USER, destino, text)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}. Verifique as credenciais e o e-mail de destino.")
        return False

# === VERIFICAÇÃO E ENVIO AUTOMÁTICO DE LEMBRETES ===

def verificar_e_enviar_lembretes_local():
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_lembretes = []

    hora_atual = datetime.now(FUSO_HORARIO_BRASIL)
    lembretes_atualizados = []

    for lembrete in all_lembretes:
        lembrete.setdefault('user_id', None)
        if not lembrete.get('enviado', False):
            data_hora_str = f"{lembrete['data']} {lembrete['hora']}"
            try:
                data_hora_lembrete = FUSO_HORARIO_BRASIL.localize(datetime.strptime(data_hora_str, "%Y-%m-%d %H:%M"))
            except Exception as e:
                st.error(f"Formato de data/hora inválido no lembrete '{lembrete.get('titulo', '')}': {e}")
                lembretes_atualizados.append(lembrete)
                continue

            if hora_atual >= data_hora_lembrete:
                email_destino = get_email_por_user_id(lembrete.get('user_id'))
                if email_destino:
                    assunto = f"Lembrete: {lembrete['titulo']}"
                    corpo = f"Olá!\n\nEste é um lembrete:\n\nTítulo: {lembrete['titulo']}\nDescrição: {lembrete['descricao']}\nData e Hora: {lembrete['data']} às {lembrete['hora']}"
                    if enviar_email(email_destino, assunto, corpo):
                        lembrete['enviado'] = True
                    else:
                        st.error(f"Falha ao enviar lembrete '{lembrete['titulo']}' para {email_destino}")
                else:
                    st.warning(f"E-mail de destino não configurado para usuário do lembrete '{lembrete.get('titulo')}'.")
        lembretes_atualizados.append(lembrete)

    salvar_lembretes(lembretes_atualizados)

# === INTERFACE STREAMLIT ===

st.set_page_config(layout="wide", page_title="Jarvis Lembretes")
st.title("⏰ Jarvis - Sistema de Lembretes Inteligente")

# Login
if not st.session_state.logged_in:
    st.header("Faça Login para Continuar")
    with st.form("login_form"):
        username_input = st.text_input("Nome de Usuário")
        password_input = st.text_input("Senha", type="password")
        login_button = st.form_submit_button("Entrar")

        if login_button:
            user = get_user_by_username(username_input)
            if user and check_password(password_input, user['password_hash']):
                st.session_state.logged_in = True
                st.session_state.username = user['username']
                st.session_state.user_id = user['id']
                st.session_state.user_role = user['role']
                st.success(f"Bem-vindo, {st.session_state.username}!")
                st.rerun()
            else:
                st.error("Nome de usuário ou senha inválidos.")
    

else:
    st.sidebar.markdown(f"**Usuário:** {st.session_state.username}")
    st.sidebar.markdown(f"**Função:** {st.session_state.user_role.capitalize()}")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_id = None
        st.session_state.user_role = None
        st.rerun()

    hora_atual_brasil = datetime.now(FUSO_HORARIO_BRASIL)

    tab1, tab2, tab3 = st.tabs(["Criar Lembrete", "Meus Lembretes", "Configurações de E-mail"])

    with tab1:
        st.header("Criar Lembrete")
        with st.form("form_novo", clear_on_submit=True):
            titulo = st.text_input("Título", max_chars=100)
            descricao = st.text_area("Descrição")
            col1, col2 = st.columns(2)
            with col1:
                data = st.date_input("Data", value=hora_atual_brasil.date())
            with col2:
                hora = st.time_input("Hora", value=hora_atual_brasil.time())
            if st.form_submit_button("Adicionar"):
                if titulo:
                    adicionar_lembrete(titulo, descricao, str(data), hora.strftime("%H:%M"))
                    st.rerun()
                else:
                    st.error("Título obrigatório.")

    with tab2:
        st.header("Meus Lembretes")
        lembretes_usuario = carregar_lembretes()
        if not lembretes_usuario:
            st.info("Nenhum lembrete para este usuário.")
        else:
            try:
                df = pd.DataFrame(lembretes_usuario)
                df["Data e Hora"] = pd.to_datetime(df["data"] + " " + df["hora"], errors='coerce')
                df = df.dropna(subset=["Data e Hora"]).sort_values("Data e Hora")
                df["Enviado"] = df["enviado"].apply(lambda x: "✅ Sim" if x else "❌ Não")
                df["Data e Hora"] = df["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')

                if st.session_state.user_role == 'admin':
                    all_users = carregar_usuarios()
                    user_map = {u['id']: u['username'] for u in all_users}
                    df['Usuário'] = df['user_id'].map(user_map).fillna('Desconhecido')
                    st.dataframe(df[["titulo", "descricao", "Data e Hora", "Enviado", "Usuário"]], use_container_width=True, hide_index=True)
                else:
                    st.dataframe(df[["titulo", "descricao", "Data e Hora", "Enviado"]], use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Erro ao exibir lembretes: {e}")

        st.subheader("Editar ou Excluir")
        opcoes = {l["id"]: f"{l['titulo']} - {l['data']} {l['hora']}" for l in lembretes_usuario}
        if opcoes:
            selecionado = st.selectbox("Selecione um lembrete", list(opcoes.keys()), format_func=lambda x: opcoes[x], key="select_lembrete_to_edit")
            if selecionado:
                item = next((l for l in lembretes_usuario if l["id"] == selecionado), None)
                if item:
                    with st.form("editar_form"):
                        novo_titulo = st.text_input("Título", value=item["titulo"])
                        nova_desc = st.text_area("Descrição", value=item["descricao"])
                        data_atual = datetime.strptime(item["data"], "%Y-%m-%d")
                        hora_atual = datetime.strptime(item["hora"], "%H:%M").time()
                        col_data, col_hora = st.columns(2)
                        with col_data:
                            nova_data = st.date_input("Data", value=data_atual)
                        with col_hora:
                            nova_hora = st.time_input("Hora", value=hora_atual)
                        col1, col2 = st.columns(2)
                        if col1.form_submit_button("Salvar Alterações"):
                            editar_lembrete(item["id"], novo_titulo, nova_desc, str(nova_data), nova_hora.strftime("%H:%M"))
                            st.rerun()
                        if col2.form_submit_button("Excluir Lembrete", type="primary"):
                            excluir_lembrete(item["id"])
                            st.rerun()
                else:
                    st.warning("Selecione um lembrete válido para editar/excluir.")
            else:
                st.info("Selecione um lembrete para editar ou excluir.")
        else:
            st.info("Não há lembretes para editar ou excluir no momento.")

    with tab3:
        st.header("Configuração de E-mail")
        if st.session_state.logged_in and st.session_state.user_id:
            config_user = carregar_configuracoes_usuario(st.session_state.user_id)
            destino = config_user.get("email_destino", "")
            with st.form("email_form"):
                novo = st.text_input("E-mail para receber lembretes", value=destino)
                if st.form_submit_button("Salvar E-mail"):
                    if "@" in novo and "." in novo:
                        if salvar_configuracoes_usuario(novo):
                            st.success(f"E-mail salvo: {novo}")
                            st.rerun()
                    else:
                        st.error("E-mail inválido.")
        else:
            st.info("Faça login para configurar seu e-mail de lembretes.")

    # Área do Admin
    if st.session_state.user_role == "admin":
        st.sidebar.markdown("---")
        st.sidebar.subheader("Área do Administrador ⚙️")
        admin_tab1, admin_tab2 = st.sidebar.tabs(["Gerenciar Usuários", "Todos os Lembretes"])

        with admin_tab1:
            st.subheader("Adicionar Novo Usuário")
            with st.form("add_user_form", clear_on_submit=True):
                new_user_name = st.text_input("Nome de Usuário", key="new_user_name")
                new_user_pass = st.text_input("Senha", type="password", key="new_user_pass")
                new_user_role = st.selectbox("Função", ["normal", "admin"], key="new_user_role")
                if st.form_submit_button("Criar Usuário"):
                    if new_user_name and new_user_pass:
                        success, message = adicionar_usuario(new_user_name, new_user_pass, new_user_role)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.error("Nome de usuário e senha são obrigatórios.")

            st.subheader("Usuários Existentes")
            usuarios_existentes = carregar_usuarios()
            if usuarios_existentes:
                df_users = pd.DataFrame(usuarios_existentes)
                st.dataframe(df_users[["username", "role", "id"]], use_container_width=True, hide_index=True)

                st.markdown("---")
                st.subheader("Editar/Excluir Usuário")
                user_options_for_select = {u["id"]: u["username"] for u in usuarios_existentes}

                if user_options_for_select:
                    selected_user = st.selectbox("Selecione um usuário", list(user_options_for_select.keys()), format_func=lambda x: user_options_for_select[x], key="select_user_to_manage")
                    if selected_user:
                        user_to_edit = next((u for u in usuarios_existentes if u["id"] == selected_user), None)
                        if user_to_edit:
                            with st.form("edit_user_form"):
                                edit_username = st.text_input("Nome de Usuário", value=user_to_edit["username"], key="edit_username")
                                edit_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key="edit_password")
                                role_index = ["normal", "admin"].index(user_to_edit["role"]) if user_to_edit["role"] in ["normal", "admin"] else 0
                                edit_role = st.selectbox("Função", ["normal", "admin"], index=role_index, key="edit_role")
                                col_edit_user, col_delete_user = st.columns(2)
                                if col_edit_user.form_submit_button("Salvar Alterações do Usuário"):
                                    success, message = editar_usuario(user_to_edit["id"], edit_username, edit_password, edit_role)
                                    if success:
                                        st.success(message)
                                        st.rerun()
                                    else:
                                        st.error(message)
                                if col_delete_user.form_submit_button("Excluir Usuário e Lembretes", type="primary"):
                                    if user_to_edit["id"] == st.session_state.user_id:
                                        st.error("Você não pode excluir a si mesmo!")
                                    elif user_to_edit["role"] == "admin" and len([u for u in usuarios_existentes if u['role'] == 'admin']) == 1:
                                        st.error("Não é possível excluir o último administrador.")
                                    else:
                                        if excluir_usuario(user_to_edit["id"]):
                                            st.success("Usuário e seus lembretes excluídos.")
                                            st.rerun()
                        else:
                            st.warning("Selecione um usuário válido para gerenciar.")
                else:
                    st.info("Nenhum usuário cadastrado.")

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
                st.dataframe(df_all[["titulo", "descricao", "Data e Hora", "Enviado", "Usuário"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum lembrete no sistema.")

# Finalmente executa a verificação e envio dos lembretes
verificar_e_enviar_lembretes_local()
