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

# Carrega as variáveis de ambiente do arquivo .env (para execução LOCAL)
load_dotenv()

# --- Configurações para Armazenamento e E-mail ---
LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'

# Credenciais de e-mail carregadas do .env (remetente para execução LOCAL)
EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
# Fallback para o email de destino, se não configurado no config.json
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# --- Funções para Gerenciar Lembretes ---

def carregar_lembretes():
    """Carrega os lembretes do arquivo JSON."""
    if not os.path.exists(LEMBRETES_FILE):
        with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def salvar_lembretes(lembretes):
    """Salva os lembretes no arquivo JSON."""
    with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
        json.dump(lembretes, f, indent=4, ensure_ascii=False)

def adicionar_lembrete(titulo, descricao, data, hora):
    """Adiciona um novo lembrete à lista."""
    lembretes = carregar_lembretes()
    novo_lembrete = {
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "descricao": descricao,
        "data": data,
        "hora": hora,
        "enviado": False
    }
    lembretes.append(novo_lembrete)
    salvar_lembretes(lembretes)
    st.success("Lembrete adicionado com sucesso!")

def editar_lembrete(lembrete_id, novo_titulo, nova_descricao, nova_data, nova_hora):
    """Edita um lembrete existente pelo ID."""
    lembretes = carregar_lembretes()
    for lembrete in lembretes:
        if lembrete['id'] == lembrete_id:
            lembrete['titulo'] = novo_titulo
            lembrete['descricao'] = nova_descricao
            lembrete['data'] = nova_data
            lembrete['hora'] = nova_hora
            lembrete['enviado'] = False
            break
    salvar_lembretes(lembretes)
    st.success("Lembrete editado com sucesso!")

def excluir_lembrete(lembrete_id):
    """Exclui um lembrete pelo ID."""
    lembretes = carregar_lembretes()
    lembretes = [lembrete for lembrete in lembretes if lembrete['id'] != lembrete_id]
    salvar_lembretes(lembretes)
    st.success("Lembrete excluído com sucesso!")

# --- Funções para Gerenciar Configurações ---

def carregar_configuracoes():
    """Carrega as configurações do arquivo JSON."""
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
                salvar_configuracoes(config) # Salva para persistir o fallback se ausente
            return config
    except json.JSONDecodeError:
        config = {"email_destino": EMAIL_ADMIN_FALLBACK}
        salvar_configuracoes(config)
        return config

def salvar_configuracoes(config):
    """Salva as configurações no arquivo JSON."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# --- Funções para Envio de E-mail (para teste LOCAL) ---

def enviar_email(destinatario, assunto, corpo):
    """Tenta enviar um e-mail para o destinatário."""
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        st.warning("Credenciais de e-mail do remetente não configuradas. Verifique seu arquivo `.env`.")
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
        text = msg.as_string()
        server.sendmail(EMAIL_REMETENTE_USER, destinatario, text)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")
        st.warning("Verifique suas credenciais (usuário e senha de aplicativo do Gmail), configurações de SMTP e acesso à internet.")
        return False

# --- Lógica de Verificação de Lembretes (para execução LOCAL e feedback visual) ---
def verificar_e_enviar_lembretes_local():
    """Verifica lembretes pendentes e simula envio de e-mails para feedback visual."""
    lembretes = carregar_lembretes()
    config = carregar_configuracoes()
    email_destino_lembretes = config.get("email_destino", EMAIL_ADMIN_FALLBACK)
    
    if not email_destino_lembretes:
        st.sidebar.warning("Nenhum e-mail de destino configurado para os lembretes. Por favor, configure na aba 'Configurações de E-mail'.")
        return

    agora = datetime.now()
    lembretes_atualizados = []
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Status de Lembretes")

    lembretes_enviados_sessao = 0

    for lembrete in lembretes:
        try:
            data_hora_lembrete = datetime.strptime(f"{lembrete['data']} {lembrete['hora']}", "%Y-%m-%d %H:%M")
            if data_hora_lembrete <= agora and not lembrete['enviado']:
                # No ambiente local do Streamlit, apenas informamos que "enviaria"
                # O envio real será feito pelo GitHub Actions.
                st.sidebar.info(f"Lembrete **'{lembrete['titulo']}'** está atrasado/no horário. GitHub Actions irá enviar.")
                # Não mudamos o status 'enviado' aqui, pois a Source of Truth é o Actions
                # A menos que você queira que a interface local também "envie" e marque.
                # Se desejar que a interface local TAMBÉM envie (duplicando emails):
                # assunto = f"Lembrete: {lembrete['titulo']}"
                # corpo = f"Olá!\n\nVocê tem um lembrete pendente:\n\n**Título:** {lembrete['titulo']}\n**Descrição:** {lembrete['descricao']}\n**Data:** {lembrete['data']}\n**Hora:** {lembrete['hora']}\n\nNão se esqueça!"
                # if enviar_email(email_destino_lembretes, assunto, corpo):
                #     lembrete['enviado'] = True # Marcaria como enviado também localmente
                #     st.sidebar.success(f"Lembrete '{lembrete['titulo']}' enviado (LOCAL) para {email_destino_lembretes}!")
                #     lembretes_enviados_sessao += 1
                # else:
                #     st.sidebar.error(f"Falha ao enviar lembrete (LOCAL): '{lembrete['titulo']}'.")
            elif data_hora_lembrete > agora:
                st.sidebar.write(f"Próximo: {lembrete['titulo']} em {lembrete['data']} às {lembrete['hora']}")
            else: # Já foi enviado (assumindo que o Actions já marcou)
                st.sidebar.write(f"Enviado: {lembrete['titulo']}")
        except ValueError as e:
            st.sidebar.warning(f"Erro no formato de data/hora do lembrete '{lembrete.get('titulo', 'N/A')}': {e}. Lembrete ignorado.")
        except Exception as e:
            st.sidebar.error(f"Erro inesperado ao processar lembrete '{lembrete.get('titulo', 'N/A')}': {e}")
            
        lembretes_atualizados.append(lembrete)

    # Se a interface Streamlit não for a responsável por MUDAR o status 'enviado',
    # então o salvar_lembretes aqui serve apenas para atualizar a exibição
    # caso algum outro campo tenha sido editado sem mudança de status de envio.
    # Se o GitHub Actions é o único que atualiza o status de envio, não precisamos salvar aqui.
    # Mas para manter a consistência se edições gerais de lembrete mudarem o status para False, mantemos.
    salvar_lembretes(lembretes_atualizados) 
    
    if lembretes_enviados_sessao > 0:
        st.toast(f"{lembretes_enviados_sessao} lembrete(s) processado(s) localmente para envio.")
    else:
        st.sidebar.info("Nenhum lembrete para processar agora.")


# --- Interface Streamlit ---

st.set_page_config(layout="wide", page_title="Sistema de Lembretes ⏰")

st.title("⏰ Sistema de Lembretes Minimalista")

tab1, tab2, tab3 = st.tabs(["Criar Lembrete", "Meus Lembretes", "Configurações de E-mail"])

with tab1:
    st.header("Criar Novo Lembrete")
    with st.form("form_criar_lembrete", clear_on_submit=True):
        titulo = st.text_input("Título do Lembrete", help="Um título conciso para o seu lembrete.", max_chars=100)
        descricao = st.text_area("Descrição (Opcional)", help="Detalhes sobre o lembrete.")
        col1, col2 = st.columns(2)
        with col1:
            data = st.date_input("Data", value=datetime.now().date(), min_value=datetime.now().date())
        with col2:
            hora = st.time_input("Hora", value=datetime.now().time())
        
        submitted = st.form_submit_button("Adicionar Lembrete")
        if submitted:
            if titulo:
                adicionar_lembrete(titulo, descricao, str(data), str(hora.strftime("%H:%M")))
                st.rerun()
            else:
                st.error("O título do lembrete é obrigatório!")

with tab2:
    st.header("Meus Lembretes")
    lembretes = carregar_lembretes()

    if not lembretes:
        st.info("Nenhum lembrete cadastrado ainda. Crie um na aba 'Criar Lembrete'!")
    else:
        df_lembretes = pd.DataFrame(lembretes)
        df_lembretes['Data e Hora'] = pd.to_datetime(df_lembretes['data'] + ' ' + df_lembretes['hora'], errors='coerce')
        df_lembretes = df_lembretes.dropna(subset=['Data e Hora'])
        df_lembretes = df_lembretes.sort_values(by='Data e Hora', ascending=True)
        df_lembretes['Enviado'] = df_lembretes['enviado'].apply(lambda x: "✅ Sim" if x else "❌ Não")

        df_display = df_lembretes[['titulo', 'descricao', 'Data e Hora', 'Enviado']].rename(
            columns={'titulo': 'Título', 'descricao': 'Descrição'}
        )

        st.dataframe(df_display, hide_index=True, use_container_width=True)

        st.subheader("Editar/Excluir Lembrete")
        
        lembretes_disponiveis = carregar_lembretes()
        if lembretes_disponiveis:
            lembretes_dict = {lembrete['id']: f"{lembrete['titulo']} ({lembrete['data']} {lembrete['hora']})" for lembrete in lembretes_disponiveis}
            
            selected_lembrete_id = st.selectbox(
                "Selecione um lembrete para editar ou excluir", 
                options=list(lembretes_dict.keys()), 
                format_func=lambda x: lembretes_dict[x]
            )

            if selected_lembrete_id:
                lembrete_selecionado = next((l for l in lembretes_disponiveis if l['id'] == selected_lembrete_id), None)
                
                if lembrete_selecionado:
                    with st.form("form_editar_lembrete"):
                        st.write(f"Editando lembrete: **{lembrete_selecionado['titulo']}**")
                        
                        novo_titulo = st.text_input("Novo Título", value=lembrete_selecionado['titulo'], max_chars=100)
                        nova_descricao = st.text_area("Nova Descrição", value=lembrete_selecionado['descricao'])
                        
                        col_edit1, col_edit2 = st.columns(2)
                        with col_edit1:
                            default_date = datetime.strptime(lembrete_selecionado['data'], "%Y-%m-%d").date()
                            nova_data = st.date_input("Nova Data", value=default_date, min_value=datetime.now().date())
                        with col_edit2:
                            default_time = datetime.strptime(lembrete_selecionado['hora'], "%H:%M").time()
                            nova_hora = st.time_input("Nova Hora", value=default_time)

                        col_btns = st.columns(2)
                        with col_btns[0]:
                            submit_edit = st.form_submit_button("Salvar Edição")
                            if submit_edit:
                                if novo_titulo:
                                    editar_lembrete(selected_lembrete_id, novo_titulo, nova_descricao, str(nova_data), str(nova_hora.strftime("%H:%M")))
                                    st.rerun()
                                else:
                                    st.error("O título do lembrete não pode ser vazio!")
                        with col_btns[1]:
                            submit_delete = st.form_submit_button("Excluir Lembrete")
                            if submit_delete:
                                excluir_lembrete(selected_lembrete_id)
                                st.rerun()
        else:
            st.info("Nenhum lembrete disponível para edição ou exclusão.")


with tab3:
    st.header("Configurações de E-mail")
    st.info("O e-mail remetente e a senha de aplicativo são configurados por segurança nos bastidores.")
    
    st.subheader("E-mail para Receber Lembretes")
    config_atual = carregar_configuracoes()
    email_destino_atual = config_atual.get("email_destino", "")

    with st.form("form_config_email_destino"):
        novo_email_destino = st.text_input(
            "Digite o e-mail para onde os lembretes devem ser enviados:",
            value=email_destino_atual,
            placeholder="seu_email@exemplo.com",
            key="email_destino_input"
        )
        salvar_config_btn = st.form_submit_button("Salvar E-mail de Destino")
        if salvar_config_btn:
            if "@" in novo_email_destino and "." in novo_email_destino:
                config_atual["email_destino"] = novo_email_destino
                salvar_configuracoes(config_atual)
                st.success(f"E-mail de destino salvo: {novo_email_destino}")
                st.rerun()
            else:
                st.error("Por favor, insira um endereço de e-mail válido.")

    st.subheader("Testar Envio de E-mail")
    teste_assunto = st.text_input("Assunto do E-mail de Teste", "Teste de Lembrete Streamlit", key="test_subject")
    teste_corpo = st.text_area("Corpo do E-mail de Teste", "Este é um e-mail de teste do seu sistema de lembretes Streamlit. Se você recebeu isso, as configurações estão corretas!", key="test_body")
    
    if st.button("Enviar E-mail de Teste", key="send_test_email_btn"):
        email_para_teste = carregar_configuracoes().get("email_destino")
        if not email_para_teste:
            st.error("Por favor, configure o 'E-mail para Receber Lembretes' antes de testar.")
        elif EMAIL_REMETENTE_USER and EMAIL_REMETENTE_PASS:
            st.info(f"Tentando enviar e-mail de teste para: {email_para_teste}")
            if enviar_email(email_para_teste, teste_assunto, teste_corpo):
                st.success(f"E-mail de teste enviado com sucesso para {email_para_teste}!")
            else:
                st.error("Falha ao enviar e-mail de teste. Verifique as mensagens de erro acima.")
        else:
            st.error("As credenciais do remetente (usuário e senha de aplicativo) não estão configuradas corretamente. Verifique seu arquivo `.env`.")

# --- Executa a verificação de lembretes ao carregar a página (feedback visual LOCAL) ---
if 'lembretes_verificados_inicialmente' not in st.session_state:
    st.session_state.lembretes_verificados_inicialmente = True
    st.toast("Verificando lembretes pendentes...")
    verificar_e_enviar_lembretes_local() # Usa a função local para feedback