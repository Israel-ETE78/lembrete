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
import pytz # <<< ADICIONADO: Biblioteca para lidar com fusos horários

# Carrega variáveis do .env
load_dotenv()

# --- Definição do Fuso Horário ---
FUSO_HORARIO_BRASIL = pytz.timezone('America/Sao_Paulo') # <<< ADICIONADO

LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'

EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# ---------------- Funções de Lembretes ----------------
def commit_arquivo_json_para_github(repo_owner, repo_name, file_path, commit_message, token):
    """
    Atualiza ou cria um arquivo no repositório GitHub via API.
    """
    # Lê o conteúdo do arquivo local
    with open(file_path, 'rb') as f:
        content = f.read()
    encoded_content = base64.b64encode(content).decode()

    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    # Primeiro, verificar se o arquivo já existe (para pegar o SHA)
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        sha = response.json()["sha"]
    else:
        sha = None

    # Payload para criar/atualizar o arquivo
    data = {
        "message": commit_message,
        "content": encoded_content,
        "branch": "main"
    }
    if sha:
        data["sha"] = sha

    put_response = requests.put(api_url, headers=headers, json=data)

    if put_response.status_code in [200, 201]:
        st.success("✔️ Arquivo atualizado no GitHub com sucesso!")
    else:
        st.error(f"❌ Falha ao atualizar arquivo no GitHub: {put_response.status_code}")
        st.json(put_response.json())

def carregar_lembretes():
    if not os.path.exists(LEMBRETES_FILE):
        with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def salvar_lembretes(lembretes):
    with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
        json.dump(lembretes, f, indent=4, ensure_ascii=False)
    
    # 🔁 Commit automático no GitHub após salvar
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
    lembretes = carregar_lembretes()
    novo = {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "descricao": descricao,
        "data": data,
        "hora": hora,
        "enviado": False
    }
    lembretes.append(novo)
    salvar_lembretes(lembretes)
    st.success("Lembrete adicionado!")

def editar_lembrete(id, titulo, descricao, data, hora):
    lembretes = carregar_lembretes()
    for l in lembretes:
        if l['id'] == id:
            l['titulo'] = titulo
            l['descricao'] = descricao
            l['data'] = data
            l['hora'] = hora
            l['enviado'] = False
            break
    salvar_lembretes(lembretes)
    st.success("Lembrete atualizado!")

def excluir_lembrete(id):
    lembretes = carregar_lembretes()
    lembretes = [l for l in lembretes if l['id'] != id]
    salvar_lembretes(lembretes)
    st.success("Lembrete excluído!")

# ---------------- Funções de Config ----------------

def carregar_configuracoes():
    if not os.path.exists(CONFIG_FILE):
        config = {"email_destino": EMAIL_ADMIN_FALLBACK}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if "email_destino" not in config:
                config["email_destino"] = EMAIL_ADMIN_FALLBACK
                salvar_configuracoes(config)
            return config
    except json.JSONDecodeError:
        config = {"email_destino": EMAIL_ADMIN_FALLBACK}
        salvar_configuracoes(config)
        return config

def salvar_configuracoes(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# ---------------- Envio de E-mail ----------------

def enviar_email(destinatario, assunto, corpo):
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        st.warning("Credenciais não configuradas no .env.")
        return False
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE_USER
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_REMETENTE_USER, EMAIL_REMETENTE_PASS)
        server.sendmail(EMAIL_REMETENTE_USER, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        return False

# ---------------- Verificação ----------------

def verificar_e_enviar_lembretes_local():
    lembretes = carregar_lembretes()
    config = carregar_configuracoes()
    destino = config.get("email_destino", EMAIL_ADMIN_FALLBACK)

    if not destino:
        st.sidebar.warning("Configure o e-mail de destino.")
        return

    # <<< ALTERADO: Pega a hora atual COM o fuso horário correto
    agora = datetime.now(FUSO_HORARIO_BRASIL)
    
    mudanca_ocorreu = False

    st.sidebar.markdown("---")
    st.sidebar.subheader("Status dos Lembretes")

    for lembrete in lembretes:
        try:
            # Combina data e hora do lembrete em um objeto datetime
            datetime_lembrete_sem_fuso = datetime.strptime(f"{lembrete['data']} {lembrete['hora']}", "%Y-%m-%d %H:%M")
            # <<< ALTERADO: Associa o fuso horário ao lembrete para uma comparação justa
            datetime_lembrete_com_fuso = FUSO_HORARIO_BRASIL.localize(datetime_lembrete_sem_fuso)

            if datetime_lembrete_com_fuso <= agora and not lembrete['enviado']:
                st.sidebar.info(f"Enviando lembrete: '{lembrete['titulo']}'")
                
                # Prepara e envia o e-mail
                assunto = f"⏰ Lembrete: {lembrete['titulo']}"
                corpo = f"Olá!\n\nEste é um lembrete para:\n\nTítulo: {lembrete['titulo']}\nDescrição: {lembrete['descricao']}\nData: {lembrete['data']} às {lembrete['hora']}"
                
                if enviar_email(destino, assunto, corpo):
                    lembrete['enviado'] = True
                    mudanca_ocorreu = True
                    st.sidebar.success(f"E-mail para '{lembrete['titulo']}' enviado!")
                else:
                    st.sidebar.error(f"Falha ao enviar e-mail para '{lembrete['titulo']}'.")
            
            elif datetime_lembrete_com_fuso > agora:
                st.sidebar.write(f"Agendado: {lembrete['titulo']} - {lembrete['data']} {lembrete['hora']}")
            else: # Já foi enviado
                st.sidebar.write(f"Já enviado: {lembrete['titulo']}")

        except Exception as e:
            st.sidebar.error(f"Erro ao processar lembrete '{lembrete.get('titulo', 'Desconhecido')}': {e}")
    
    # Salva o arquivo de lembretes apenas se um e-mail foi enviado
    if mudanca_ocorreu:
        salvar_lembretes(lembretes)


# ---------------- Interface ----------------

st.set_page_config(layout="wide", page_title="Jarvis Lembretes")
st.title("⏰ Jarvis - Sistema de Lembretes Inteligente")

# <<< ALTERADO: Define a hora atual com fuso para os valores padrão dos campos
hora_atual_brasil = datetime.now(FUSO_HORARIO_BRASIL)

tab1, tab2, tab3 = st.tabs(["Criar Lembrete", "Meus Lembretes", "Configurações de E-mail"])

with tab1:
    st.header("Criar Lembrete")
    with st.form("form_novo", clear_on_submit=True):
        titulo = st.text_input("Título", max_chars=100)
        descricao = st.text_area("Descrição")
        col1, col2 = st.columns(2)
        with col1:
            # <<< ALTERADO: Usa a data correta como padrão
            data = st.date_input("Data", value=hora_atual_brasil.date())
        with col2:
            # <<< ALTERADO: Usa a hora correta como padrão
            hora = st.time_input("Hora", value=hora_atual_brasil.time())
        if st.form_submit_button("Adicionar"):
            if titulo:
                adicionar_lembrete(titulo, descricao, str(data), hora.strftime("%H:%M"))
                st.rerun()
            else:
                st.error("Título obrigatório.")

with tab2:
    st.header("Meus Lembretes")
    lembretes = carregar_lembretes()
    if not lembretes:
        st.info("Nenhum lembrete.")
    else:
        # Tenta converter para DataFrame, tratando possíveis erros
        try:
            df = pd.DataFrame(lembretes)
            df["Data e Hora"] = pd.to_datetime(df["data"] + " " + df["hora"], errors='coerce')
            df = df.dropna(subset=["Data e Hora"]).sort_values("Data e Hora")
            df["Enviado"] = df["enviado"].apply(lambda x: "✅ Sim" if x else "❌ Não")
            df["Data e Hora"] = df["Data e Hora"].dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df[["titulo", "descricao", "Data e Hora", "Enviado"]], use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Não foi possível exibir os lembretes. Verifique o arquivo JSON. Erro: {e}")


        st.subheader("Editar ou Excluir")
        opcoes = {l["id"]: f"{l['titulo']} - {l['data']} {l['hora']}" for l in lembretes}
        selecionado = st.selectbox("Selecione um lembrete", list(opcoes.keys()), format_func=lambda x: opcoes[x])

        if selecionado:
            item = next((l for l in lembretes if l["id"] == selecionado), None)
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

with tab3:
    st.header("Configuração de E-mail")
    config = carregar_configuracoes()
    destino = config.get("email_destino", "")
    with st.form("email_form"):
        novo = st.text_input("E-mail para receber lembretes", value=destino)
        if st.form_submit_button("Salvar E-mail"):
            if "@" in novo and "." in novo:
                config["email_destino"] = novo
                salvar_configuracoes(config)
                st.success(f"E-mail salvo: {novo}")
                st.rerun()
            else:
                st.error("E-mail inválido.")

# Verificação de lembretes SEMPRE na renderização
verificar_e_enviar_lembretes_local()