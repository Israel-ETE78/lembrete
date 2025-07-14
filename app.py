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
CONFIG_FILE = 'config.json' # This file will now store per-user email configurations
USUARIOS_FILE = 'usuarios.json'

EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# --- Gerenciamento de Sessão ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.user_role = None

# ---------------- Funções de Lembretes ----------------
def commit_arquivo_json_para_github(repo_owner, repo_name, file_path, commit_message, token):
    """
    Atualiza ou cria um arquivo no repositório GitHub via API.
    """
    # Lê o conteúdo do arquivo local
    with open(file_path, 'rb') as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode()

    # URL da API do GitHub para o arquivo
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"
    
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json"
    }

    # Tenta obter o SHA do arquivo se ele já existe
    sha = None
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        if response.status_code == 200:
            sha = response.json().get("sha")
    except requests.exceptions.RequestException:
        pass # Ignora erro se o arquivo não existe ou não pode ser acessado

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
        st.error(f"Erro ao commitar {file_path} para o GitHub: {e}")
        return False


def carregar_lembretes():
    if not os.path.exists(LEMBRETES_FILE):
        with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes = json.load(f)
            # Garante que todo lembrete tenha 'user_id' para evitar KeyError em DataFrames futuros
            for lembrete in all_lembretes:
                lembrete.setdefault('user_id', None) # Define como None se não existir
            
            if st.session_state.logged_in and st.session_state.user_role == 'admin':
                return all_lembretes
            elif st.session_state.logged_in:
                return [l for l in all_lembretes if l.get('user_id') == st.session_state.user_id]
            else:
                return []
    except json.JSONDecodeError:
        return []

def salvar_lembretes(lembretes):
    with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
        json.dump(lembretes, f, indent=4, ensure_ascii=False)
    
    token = os.getenv("GITHUB_TOKEN")
    if token:
        commit_arquivo_json_para_github(
            repo_owner="Israel-ETE78",
            repo_name="lembrete",
            file_path=LEMBRETES_FILE,
            commit_message="🔄 Atualização automática dos lembretes",
            token=token
        )
    else:
        st.warning("⚠️ GITHUB_TOKEN não encontrado. Commit automático não realizado.")

def adicionar_lembrete(titulo, descricao, data, hora):
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_lembretes = []

    novo = {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "descricao": descricao,
        "data": data,
        "hora": hora,
        "enviado": False,
        "user_id": st.session_state.user_id
    }
    all_lembretes.append(novo)
    salvar_lembretes(all_lembretes)
    st.success("Lembrete adicionado!")

def editar_lembrete(id, titulo, descricao, data, hora):
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        st.error("Erro: Arquivo de lembretes não encontrado ou corrompido ao editar.")
        return

    found = False
    for l in all_lembretes:
        if l['id'] == id:
            if st.session_state.user_role == 'admin' or l.get('user_id') == st.session_state.user_id:
                l['titulo'] = titulo
                l['descricao'] = descricao
                l['data'] = data
                l['hora'] = hora
                l['enviado'] = False
                found = True
                break
            else:
                st.warning("Você não tem permissão para editar este lembrete.")
                return

    if found:
        salvar_lembretes(all_lembretes)
        st.success("Lembrete atualizado!")
    else:
        st.error("Lembrete não encontrado para edição.")

def excluir_lembrete(id):
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        st.error("Erro: Arquivo de lembretes não encontrado ou corrompido ao excluir.")
        return

    lembretes_apos_exclusao = []
    removed = False
    for l in all_lembretes:
        if l['id'] == id:
            if st.session_state.user_role == 'admin' or l.get('user_id') == st.session_state.user_id:
                removed = True
                continue
            else:
                st.warning("Você não tem permissão para excluir este lembrete.")
                return
        lembretes_apos_exclusao.append(l)

    if removed:
        salvar_lembretes(lembretes_apos_exclusao)
        st.success("Lembrete excluído!")
    else:
        st.error("Lembrete não encontrado para exclusão.")


# ---------------- Funções de Gerenciamento de Usuários ----------------

def hash_password(password):
    """Gera o hash de uma senha."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')

def check_password(password, hashed_password):
    """Verifica se uma senha corresponde ao seu hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def carregar_usuarios():
    """Carrega os dados dos usuários do arquivo JSON."""
    if not os.path.exists(USUARIOS_FILE):
        admin_id = str(uuid.uuid4())
        initial_users = [{
            "id": admin_id,
            "username": "admin",
            "password_hash": hash_password("admin123"),
            "role": "admin"
        }]
        with open(USUARIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(initial_users, f, indent=4, ensure_ascii=False)
        return initial_users
    try:
        with open(USUARIOS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        st.error(f"Erro ao carregar o arquivo de usuários '{USUARIOS_FILE}'. Criando um novo.")
        return []

def salvar_usuarios(usuarios):
    """Salva os dados dos usuários no arquivo JSON."""
    with open(USUARIOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(usuarios, f, indent=4, ensure_ascii=False)
    
    token = os.getenv("GITHUB_TOKEN")
    if token:
        commit_arquivo_json_para_github(
            repo_owner="Israel-ETE78",
            repo_name="lembrete",
            file_path=USUARIOS_FILE,
            commit_message="🔄 Atualização automática dos usuários",
            token=token
        )
    else:
        st.warning("⚠️ GITHUB_TOKEN não encontrado. Commit automático de usuários não realizado.")

def get_user_by_username(username):
    """Retorna os dados de um usuário pelo nome de usuário."""
    usuarios = carregar_usuarios()
    for user in usuarios:
        if user['username'] == username:
            return user
    return None

def adicionar_usuario(username, password, role):
    """Adiciona um novo usuário ao sistema."""
    usuarios = carregar_usuarios()
    if any(u['username'] == username for u in usuarios):
        return False, "Nome de usuário já existe."
    
    novo_usuario = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": hash_password(password),
        "role": role
    }
    usuarios.append(novo_usuario)
    salvar_usuarios(usuarios)
    return True, "Usuário adicionado com sucesso!"

def editar_usuario(user_id, new_username, new_password, new_role):
    """Edita um usuário existente."""
    usuarios = carregar_usuarios()
    for i, user in enumerate(usuarios):
        if user['id'] == user_id:
            usuarios[i]['username'] = new_username
            if new_password:
                usuarios[i]['password_hash'] = hash_password(new_password)
            usuarios[i]['role'] = new_role
            salvar_usuarios(usuarios)
            return True, "Usuário atualizado com sucesso!"
    return False, "Usuário não encontrado."

def excluir_usuario(user_id):
    """Exclui um usuário e todos os seus lembretes."""
    usuarios = carregar_usuarios()
    
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_lembretes_system = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_lembretes_system = []

    usuarios_restantes = [u for u in usuarios if u['id'] != user_id]
    lembretes_restantes = [l for l in all_lembretes_system if l.get('user_id') != user_id]

    if len(usuarios_restantes) < len(usuarios):
        salvar_usuarios(usuarios_restantes)
        st.success(f"Usuário excluído com sucesso! {len(usuarios) - len(usuarios_restantes)} usuários removidos.")
        
        if len(lembretes_restantes) < len(all_lembretes_system):
            salvar_lembretes(lembretes_restantes)
            st.warning(f"Todos os lembretes do usuário excluído também foram removidos. {len(all_lembretes_system) - len(lembretes_restantes)} lembretes removidos.")
        return True
    return False

# ---------------- Funções de Config (Per-User Email) ----------------

# Função para carregar a configuração (e-mail) do usuário logado
def carregar_configuracoes_usuario(user_id):
    """Carrega a configuração (e-mail) de um usuário específico."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get(user_id, {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def salvar_configuracoes_usuario(email_destino):
    # Carrega o config atual
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}
    # Atualiza o e-mail do usuário logado
    if st.session_state.user_id: # Only save if a user is logged in
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
    return True # Indicate success

def get_email_por_user_id(user_id):
    """Retorna o e-mail de lembrete salvo por um usuário específico."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get(user_id, {}).get("email_destino", EMAIL_ADMIN_FALLBACK)
    except (FileNotFoundError, json.JSONDecodeError):
        return EMAIL_ADMIN_FALLBACK

# ---------------- Funções de Envio de E-mail ----------------
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

def verificar_e_enviar_lembretes_local():
    # Esta função precisa de TODOS os lembretes do sistema, não apenas os do usuário logado
    
    lembretes_para_salvar = []
    
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            all_system_lembretes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        all_system_lembretes = []

    current_time_brasil = datetime.now(FUSO_HORARIO_BRASIL)
    
    for lembrete in all_system_lembretes:
        lembrete.setdefault('user_id', None) # Define como None se não existir
        email_destino = get_email_por_user_id(lembrete.get("user_id")) # Get email for THIS reminder's user
        
        if not lembrete['enviado']:
            data_hora_lembrete_str = f"{lembrete['data']} {lembrete['hora']}"
            
            try:
                data_hora_lembrete = FUSO_HORARIO_BRASIL.localize(datetime.strptime(data_hora_lembrete_str, "%Y-%m-%d %H:%M"))

                if current_time_brasil >= data_hora_lembrete:
                    if email_destino: # Ensure there is a destination email
                        assunto = f"Lembrete: {lembrete['titulo']}"
                        corpo = f"Olá!\n\nEste é um lembrete:\n\nTítulo: {lembrete['titulo']}\nDescrição: {lembrete['descricao']}\n\nData e Hora: {lembrete['data']} às {lembrete['hora']}"
                        
                        if enviar_email(email_destino, assunto, corpo):
                            lembrete['enviado'] = True
                        else:
                            st.error(f"Falha ao enviar lembrete '{lembrete['titulo']}'.")
                    else:
                        st.warning(f"Lembrete '{lembrete['titulo']}' não enviado: E-mail de destino não configurado para o usuário {lembrete.get('user_id') or 'sem usuário'}.")
            except ValueError as e:
                st.error(f"Erro no formato de data/hora do lembrete '{lembrete['titulo']}': {e}")
            except pytz.exceptions.AmbiguousTimeError:
                st.error(f"Erro de horário ambíguo para o lembrete '{lembrete['titulo']}'. Verifique o horário de verão.")
            except pytz.exceptions.NonExistentTimeError:
                st.error(f"Erro de horário inexistente para o lembrete '{lembrete['titulo']}'. Verifique o horário de verão.")
        lembretes_para_salvar.append(lembrete)

    salvar_lembretes(lembretes_para_salvar)


# ---------------- Interface do Streamlit ----------------
st.set_page_config(layout="wide", page_title="Jarvis Lembretes")
st.title("⏰ Jarvis - Sistema de Lembretes Inteligente")

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
    st.info("O usuário administrador padrão é 'admin' com a senha 'admin123'. Altere-a após o primeiro login.")

else:
    st.sidebar.markdown(f"**Usuário:** {st.session_state.username}")
    st.sidebar.markdown(f"**Função:** {st.session_state.user_role.capitalize()}")
    if st.sidebar.button("Sair", type="secondary"):
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
        lembretes_do_usuario = carregar_lembretes()
        if not lembretes_do_usuario:
            st.info("Nenhum lembrete para este usuário.")
        else:
            try:
                df = pd.DataFrame(lembretes_do_usuario)
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
                st.error(f"Não foi possível exibir os lembretes. Verifique o arquivo JSON. Erro: {e}")

        st.subheader("Editar ou Excluir")
        opcoes = {l["id"]: f"{l['titulo']} - {l['data']} {l['hora']}" for l in lembretes_do_usuario}
        
        if opcoes:
            selecionado = st.selectbox("Selecione um lembrete", list(opcoes.keys()), format_func=lambda x: opcoes[x], key="select_lembrete_to_edit")

            if selecionado:
                item = next((l for l in lembretes_do_usuario if l["id"] == selecionado), None)
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
        # Ensure user is logged in to get their config
        if st.session_state.logged_in and st.session_state.user_id:
            config_user = carregar_configuracoes_usuario(st.session_state.user_id) # Call the global function
            destino = config_user.get("email_destino", "")
            with st.form("email_form"):
                novo = st.text_input("E-mail para receber lembretes", value=destino)
                if st.form_submit_button("Salvar E-mail"):
                    if "@" in novo and "." in novo:
                        if salvar_configuracoes_usuario(novo): # Check if saving was successful
                            st.success(f"E-mail salvo: {novo}")
                            st.rerun()
                    else:
                        st.error("E-mail inválido.")
        else:
            st.info("Faça login para configurar seu e-mail de lembretes.")


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
                
                user_options_for_select = {}
                for u in usuarios_existentes:
                    user_options_for_select[u["id"]] = u["username"]

                if user_options_for_select:
                    selected_user_to_manage = st.selectbox("Selecione um usuário", list(user_options_for_select.keys()), format_func=lambda x: user_options_for_select[x], key="select_user_to_manage")

                    if selected_user_to_manage:
                        user_to_edit = next((u for u in usuarios_existentes if u["id"] == selected_user_to_manage), None)
                        if user_to_edit:
                            with st.form("edit_user_form"):
                                edit_username = st.text_input("Nome de Usuário", value=user_to_edit["username"], key="edit_username")
                                edit_password = st.text_input("Nova Senha (deixe em branco para não alterar)", type="password", key="edit_password")
                                try:
                                    role_index = ["normal", "admin"].index(user_to_edit["role"])
                                except ValueError:
                                    role_index = 0
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
                                            st.rerun()
                        else:
                            st.warning("Selecione um usuário válido para gerenciar.")
                else:
                    st.info("Nenhum usuário cadastrado.")

        with admin_tab2:
            st.subheader("Todos os Lembretes do Sistema")
            try:
                with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
                    all_lembretes_admin_view = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                all_lembretes_admin_view = []

            # Ensure all reminders have 'user_id' before creating the DataFrame
            for lembrete in all_lembretes_admin_view:
                lembrete.setdefault('user_id', None) # If 'user_id' does not exist, add with None value

            if all_lembretes_admin_view:
                df_all_lembretes = pd.DataFrame(all_lembretes_admin_view)
                df_all_lembretes["Data e Hora"] = pd.to_datetime(df_all_lembretes["data"] + " " + df_all_lembretes["hora"], errors='coerce')
                df_all_lembretes = df_all_lembretes.dropna(subset=["Data e Hora"]).sort_values("Data e Hora")
                df_all_lembretes["Enviado"] = df_all_lembretes["enviado"].apply(lambda x: "✅ Sim" if x else "❌ Não")
                df_all_lembretes["Data e Hora"] = df_all_lembretes["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')
                
                # Display all reminders for admin view
                all_users = carregar_usuarios()
                user_map = {u['id']: u['username'] for u in all_users}
                df_all_lembretes['Usuário'] = df_all_lembretes['user_id'].map(user_map).fillna('Desconhecido')
                st.dataframe(df_all_lembretes[["titulo", "descricao", "Data e Hora", "Enviado", "Usuário"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum lembrete no sistema.")

verificar_e_enviar_lembretes_local() # This call needs to be at the very end to ensure all functions are defined and UI is built.