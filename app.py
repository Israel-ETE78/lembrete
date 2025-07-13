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

# Carrega variáveis do .env
load_dotenv()

LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'

EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# ---------------- Funções de Lembretes ----------------

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

    agora = datetime.now()
    atualizados = []

    st.sidebar.markdown("---")
    st.sidebar.subheader("Status dos Lembretes")

    for lembrete in lembretes:
        try:
            dh = datetime.strptime(f"{lembrete['data']} {lembrete['hora']}", "%Y-%m-%d %H:%M")
            if dh <= agora and not lembrete['enviado']:
                st.sidebar.info(f"Lembrete: '{lembrete['titulo']}' está no horário (envia).")
            elif dh > agora:
                st.sidebar.write(f"Agendado: {lembrete['titulo']} - {lembrete['data']} {lembrete['hora']}")
            else:
                st.sidebar.write(f"Enviado: {lembrete['titulo']}")
        except Exception as e:
            st.sidebar.error(f"Erro: {e}")
        atualizados.append(lembrete)

    salvar_lembretes(atualizados)

# ---------------- Interface ----------------

st.set_page_config(layout="wide", page_title="Jarvis Lembretes")
st.title("⏰ Jarvis - Sistema de Lembretes Inteligente")


tab1, tab2, tab3 = st.tabs(["Criar Lembrete", "Meus Lembretes", "Configurações de E-mail"])

with tab1:
    st.header("Criar Lembrete")
    with st.form("form_novo", clear_on_submit=True):
        titulo = st.text_input("Título", max_chars=100)
        descricao = st.text_area("Descrição")
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data", value=datetime.now().date())
        with col2:
            hora = st.time_input("Hora", value=datetime.now().time())
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
        df = pd.DataFrame(lembretes)
        df["Data e Hora"] = pd.to_datetime(df["data"] + " " + df["hora"], errors="coerce")
        df = df.dropna(subset=["Data e Hora"]).sort_values("Data e Hora")
        df["Enviado"] = df["enviado"].apply(lambda x: "✅" if x else "❌")
        st.dataframe(df[["titulo", "descricao", "Data e Hora", "Enviado"]], hide_index=True)

        st.subheader("Editar ou Excluir")
        opcoes = {l["id"]: f"{l['titulo']} - {l['data']} {l['hora']}" for l in lembretes}
        selecionado = st.selectbox("Selecione um lembrete", list(opcoes.keys()), format_func=lambda x: opcoes[x])

        if selecionado:
            item = next((l for l in lembretes if l["id"] == selecionado), None)
            with st.form("editar_form"):
                novo_titulo = st.text_input("Título", value=item["titulo"])
                nova_desc = st.text_area("Descrição", value=item["descricao"])
                nova_data = st.date_input("Data", value=datetime.strptime(item["data"], "%Y-%m-%d"))
                nova_hora = st.time_input("Hora", value=datetime.strptime(item["hora"], "%H:%M").time())
                col1, col2 = st.columns(2)
                if col1.form_submit_button("Salvar"):
                    editar_lembrete(item["id"], novo_titulo, nova_desc, str(nova_data), nova_hora.strftime("%H:%M"))
                    st.rerun()
                if col2.form_submit_button("Excluir"):
                    excluir_lembrete(item["id"])
                    st.rerun()

with tab3:
    st.header("Configuração de E-mail")
    config = carregar_configuracoes()
    destino = config.get("email_destino", "")
    with st.form("email_form"):
        novo = st.text_input("E-mail para receber lembretes", value=destino)
        if st.form_submit_button("Salvar"):
            if "@" in novo and "." in novo:
                config["email_destino"] = novo
                salvar_configuracoes(config)
                st.success(f"E-mail salvo: {novo}")
                st.rerun()
            else:
                st.error("E-mail inválido.")

if 'lembretes_verificados_inicialmente' not in st.session_state:
    st.session_state.lembretes_verificados_inicialmente = True
    st.toast("Verificando lembretes...")
    verificar_e_enviar_lembretes_local()
