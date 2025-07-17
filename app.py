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
import subprocess # Importar o módulo subprocess

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


# === FUNÇÕES AUXILIARES GERAIS ===
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
            st.error("Erro: GITHUB_TOKEN não configurado como secret no Streamlit Cloud.")
            print("DEBUG: GITHUB_TOKEN não encontrado nas variáveis de ambiente.")
            return

        # Configura o git
        subprocess.run(["git", "config", "user.name", "Streamlit Cloud Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "streamlit-bot@example.com"], check=True)

        # 3. Adiciona o arquivo às mudanças do Git
        subprocess.run(["git", "add", arquivo], check=True)
        print(f"DEBUG: {arquivo} adicionado ao staging do Git.")

        # 4. Verifica se há algo para commitar antes de tentar commitar
        result_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if not result_status.stdout.strip():
            print("DEBUG: Nenhuma alteração para commitar. Ignorando commit e push.")
            return # Não há alterações, então não precisa commitar nem fazer push

        # 5. Faz o commit
        subprocess.run(["git", "commit", "-m", mensagem_commit], check=True)
        print(f"DEBUG: Commit realizado com a mensagem: '{mensagem_commit}'.")

        # 6. Faz o push para o repositório remoto
        # A URL do repositório deve estar no formato token@github.com/usuario/repositorio.git
        # O Streamlit já clona o repo, então 'origin' já deve estar configurado.
        current_repo_url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout.strip()
        # Modifica a URL para incluir o token para autenticação HTTP
        # Ex: de 'https://github.com/user/repo.git' para 'https://oauth2:YOUR_TOKEN@github.com/user/repo.git'
        # ou de 'git@github.com:user/repo.git' para 'https://oauth2:YOUR_TOKEN@github.com/user/repo.git'
        # O GitHub recomenda 'oauth2' como username para tokens
        
        # Tentativa mais robusta de construir a URL com token
        # Substitui a parte de autenticação se já existir, ou adiciona se não
        if "https://" in current_repo_url:
            parts = current_repo_url.split("//")
            auth_part = f"oauth2:{github_token}@"
            push_url = f"{parts[0]}//{auth_part}{parts[1]}"
        elif "git@" in current_repo_url: # Se for um SSH URL, converte para HTTPS com token
            repo_path = current_repo_url.split("git@github.com:")[1]
            push_url = f"https://oauth2:{github_token}@github.com/{repo_path}"
        else:
            # Caso a URL esteja em outro formato ou seja complexa, tentamos com a original e esperamos que o git
            # use o credential helper configurado via token, se houver.
            # No entanto, para Streamlit, explicitar na URL é mais seguro.
            st.warning("Não foi possível inferir a URL de push para incluir o token de forma segura. O push pode falhar.")
            push_url = current_repo_url # Tenta o push com a URL original, esperando que credenciais estejam configuradas
        
        subprocess.run(["git", "push", push_url], check=True)
        print(f"DEBUG: Alterações de {arquivo} empurradas para o GitHub.")

    except subprocess.CalledProcessError as e:
        st.error(f"Erro no Git ao salvar {arquivo}: {e.stderr.strip()}")
        print(f"DEBUG: Erro do subprocesso Git: {e.stderr.strip()}")
    except Exception as e:
        st.error(f"Erro inesperado ao salvar {arquivo}: {e}")
        print(f"DEBUG: Erro inesperado ao salvar arquivo: {e}")

# As demais funções (carregar_lembretes, salvar_lembretes, etc.) chamam salvar_com_commit_json
# portanto, elas se beneficiarão automaticamente desta mudança.