import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz # Importa a biblioteca para fusos horários
from dotenv import load_dotenv # Importa para carregar .env localmente
import subprocess # NOVO: Importa a biblioteca para executar comandos de sistema

# --- Configurações Iniciais ---
# Carrega variáveis do .env (necessário para execução local e debug)
load_dotenv()

# Definição do Fuso Horário
FUSO_HORARIO_BRASIL = pytz.timezone('America/Sao_Paulo')

# Caminhos dos arquivos (relativos ao diretório de execução)
LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'

# Credenciais de e-mail (serão lidas das variáveis de ambiente ou .env)
EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# --- DEBUG PRINTS (ÚTEIS PARA RASTREAMENTO, REMOVA QUANDO ESTIVER TUDO OK) ---
print("\n--- DEBUG INFORMATION (scheduler_email_sender.py) ---")
print(f"DEBUG: Caminho LEMBRETES_FILE: '{os.path.abspath(LEMBRETES_FILE)}'")
print(f"DEBUG: Caminho CONFIG_FILE: '{os.path.abspath(CONFIG_FILE)}'")
print(f"DEBUG: Valor de GMAIL_USER: '{EMAIL_REMETENTE_USER}' (Configurado? {bool(EMAIL_REMETENTE_USER)})")
print(f"DEBUG: Valor de GMAIL_APP_PASSWORD: '{EMAIL_REMETENTE_PASS[:5]}...' (Configurado? {bool(EMAIL_REMETENTE_PASS)})") # Oculta a maioria da senha por segurança
print(f"DEBUG: Valor de EMAIL_ADMIN_FALLBACK: '{EMAIL_ADMIN_FALLBACK}' (Configurado? {bool(EMAIL_ADMIN_FALLBACK)})")

# Tentativa de carregar config.json para debug adicional
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        debug_config_data = json.load(f)
        debug_email_destino_from_file = debug_config_data.get("email_destino")
        print(f"DEBUG: email_destino no config.json: '{debug_email_destino_from_file}' (Configurado? {bool(debug_email_destino_from_file)})")
except FileNotFoundError:
    print(f"DEBUG: Arquivo {CONFIG_FILE} não encontrado. Será usado o fallback.")
except json.JSONDecodeError:
    print(f"DEBUG: Arquivo {CONFIG_FILE} corrompido ou vazio. Será usado o fallback.")
except Exception as e:
    print(f"DEBUG: Erro ao ler {CONFIG_FILE} para debug: {e}")
print("---------------------------------------------------\n")
# --- FIM DEBUG PRINTS ---


# --- Funções de Carregamento/Salvamento de Arquivos ---
def carregar_lembretes():
    if not os.path.exists(LEMBRETES_FILE):
        print(f"Aviso: O arquivo '{LEMBRETES_FILE}' não foi encontrado. Retornando lista vazia.")
        return []
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list): # Garante que o JSON é uma lista
                print(f"Aviso: O arquivo '{LEMBRETES_FILE}' contém dados inválidos (não é uma lista). Retornando lista vazia.")
                return []
            return data
    except json.JSONDecodeError:
        print(f"Aviso: O arquivo '{LEMBRETES_FILE}' está vazio ou corrompido. Retornando lista vazia.")
        return []
    except Exception as e:
        print(f"Erro inesperado ao carregar '{LEMBRETES_FILE}': {e}. Retornando lista vazia.")
        return []

# NOVA FUNÇÃO: Salva lembretes e faz commit/push
def salvar_lembretes_e_commitar(lembretes_data, mensagem_commit):
    """Salva os dados de lembretes no lembretes.json e faz commit/push para o GitHub."""
    try:
        # Salva o arquivo localmente
        with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
            json.dump(lembretes_data, f, indent=4, ensure_ascii=False)
        print(f"DEBUG: Arquivo {LEMBRETES_FILE} salvo localmente no Actions.")

        # Configura as credenciais do Git
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            print("ERRO: GITHUB_TOKEN não configurado para o scheduler. Não é possível fazer o commit.")
            return

        subprocess.run(["git", "config", "user.name", "GitHub Actions Bot"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)

        # Adiciona o arquivo modificado
        subprocess.run(["git", "add", LEMBRETES_FILE], check=True)
        print(f"DEBUG: {LEMBRETES_FILE} adicionado ao staging do Git no Actions.")
        
        # Verifica se há algo para commitar antes de tentar commitar
        # git diff-index --quiet HEAD -- retorna 0 se não há mudanças, 1 se há
        try:
            subprocess.run(["git", "diff-index", "--quiet", "HEAD", "--"], check=True)
            print("DEBUG: Nenhuma alteração real para commitar. Ignorando commit e push no Actions.")
            return # Não há alterações, então não precisa commitar nem fazer push
        except subprocess.CalledProcessError:
            # Há alterações, continue para commit
            pass

        # Faz o commit
        subprocess.run(["git", "commit", "-m", mensagem_commit], check=True)
        print(f"DEBUG: Commit realizado no Actions com a mensagem: '{mensagem_commit}'.")

        # Faz o push para o repositório remoto usando o token para autenticação
        repo_owner_repo = os.getenv("GITHUB_REPOSITORY") # Formato: "usuario/repositorio"
        if not repo_owner_repo:
            print("ERRO: Variável de ambiente GITHUB_REPOSITORY não encontrada. Não é possível fazer o push.")
            return

        push_url = f"https://oauth2:{github_token}@github.com/{repo_owner_repo}.git"
        subprocess.run(["git", "push", push_url], check=True)
        print(f"DEBUG: Alterações de {LEMBRETES_FILE} empurradas para o GitHub pelo Actions.")

    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip() if e.stderr else e.output.strip()
        print(f"ERRO: Git falhou no Actions ao salvar {LEMBRETES_FILE}: {error_output}. Verifique as permissões do GITHUB_TOKEN no workflow.")
    except Exception as e:
        print(f"ERRO: Erro inesperado ao salvar {LEMBRETES_FILE} no Actions: {e}")


def carregar_configuracoes():
    if not os.path.exists(CONFIG_FILE):
        print(f"Aviso: O arquivo '{CONFIG_FILE}' não existe. Retornando configurações padrão com fallback.")
        return {"email_destino": EMAIL_ADMIN_FALLBACK}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if "email_destino" not in config:
                print(f"Aviso: 'email_destino' não encontrado em '{CONFIG_FILE}'. Usando fallback.")
                config["email_destino"] = EMAIL_ADMIN_FALLBACK
            return config
    except json.JSONDecodeError:
        print(f"Aviso: O arquivo '{CONFIG_FILE}' está vazio ou corrompido. Retornando configurações padrão com fallback.")
        return {"email_destino": EMAIL_ADMIN_FALLBACK}
    except Exception as e:
        print(f"Erro inesperado ao carregar '{CONFIG_FILE}': {e}. Retornando configurações padrão.")
        return {"email_destino": EMAIL_ADMIN_FALLBACK}

# --- Funções de Envio de E-mail ---
def enviar_email(destinatario, assunto, corpo):
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        print("Erro: Credenciais de e-mail do remetente (GMAIL_USER ou GMAIL_APP_PASSWORD) não configuradas.")
        return False

    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE_USER
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo, 'plain', 'utf-8'))

    try:
        # Usando 'smtp.gmail.com' e porta 587 com STARTTLS (comum para Gmail)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Inicia a segurança TLS
        server.login(EMAIL_REMETENTE_USER, EMAIL_REMETENTE_PASS)
        text = msg.as_string()
        server.sendmail(EMAIL_REMETENTE_USER, destinatario, text)
        server.quit()
        print(f"Lembrete enviado com sucesso para {destinatario}: '{assunto}'")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"ERRO DE AUTENTICAÇÃO SMTP: Verifique GMAIL_USER e GMAIL_APP_PASSWORD (senha de aplicativo). Detalhes: {e}")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"ERRO DE CONEXÃO SMTP: O servidor desconectou. Verifique sua rede ou configurações do Gmail. Detalhes: {e}")
        return False
    except Exception as e:
        print(f"Erro inesperado ao enviar e-mail para {destinatario}: {e}")
        return False

# --- Lógica Principal de Verificação e Envio ---
def main():
    print(f"[{datetime.now(FUSO_HORARIO_BRASIL).strftime('%Y-%m-%d %H:%M:%S')}] Iniciando verificação de lembretes...")
    
    lembretes_atuais = carregar_lembretes() # Renomeado para evitar conflito
    config = carregar_configuracoes()
    email_destino_lembretes = config.get("email_destino", EMAIL_ADMIN_FALLBACK)
    
    if not email_destino_lembretes:
        print("Aviso: E-mail de destino não configurado no 'config.json' e nenhum fallback disponível. Não será possível enviar e-mails.")
        return
    
    if not (EMAIL_REMETENTE_USER and EMAIL_REMETENTE_PASS):
        print("Aviso: Credenciais do remetente (GMAIL_USER e GMAIL_APP_PASSWORD) não configuradas. Não será possível enviar e-mails.")
        return

    # Obtém a hora atual com o fuso horário correto
    agora = datetime.now(FUSO_HORARIO_BRASIL)
    lembretes_enviados_nesta_execucao = 0

    for lembrete in lembretes_atuais:
        try:
            # Pega a data e hora do lembrete, garantindo que são strings
            lembrete_data_str = str(lembrete.get('data', ''))
            lembrete_hora_str = str(lembrete.get('hora', ''))

            if not lembrete_data_str or not lembrete_hora_str:
                print(f"Aviso: Lembrete '{lembrete.get('titulo', 'N/A')}' (ID: {lembrete.get('id', 'N/A')}) tem data/hora inválida ou ausente. Ignorando.")
                continue # Pula para o próximo lembrete

            # Converte a string de data/hora em um objeto datetime e o localiza no fuso horário
            data_hora_lembrete_naive = datetime.strptime(f"{lembrete_data_str} {lembrete_hora_str}", "%Y-%m-%d %H:%M")
            data_hora_lembrete = FUSO_HORARIO_BRASIL.localize(data_hora_lembrete_naive)
            
            # Verifica se o lembrete já passou ou está no momento de envio e ainda não foi enviado
            if data_hora_lembrete <= agora and not lembrete.get('enviado', False):
                assunto = f"⏰ Lembrete: {lembrete['titulo']}"
                corpo = (
                    f"Olá!\n\nVocê tem um lembrete pendente:\n\n"
                    f"Título: {lembrete['titulo']}\n"
                    f"Descrição: {lembrete['descricao']}\n"
                    f"Data: {lembrete['data']} às {lembrete['hora']}\n\n"
                    f"Não se esqueça!"
                )
                
                print(f"Processando lembrete para envio: '{lembrete['titulo']}' (ID: {lembrete['id']})")
                if enviar_email(email_destino_lembretes, assunto, corpo):
                    lembrete['enviado'] = True # Marca como enviado
                    lembretes_enviados_nesta_execucao += 1
                else:
                    print(f"Falha ao enviar lembrete: '{lembrete['titulo']}'. O status 'enviado' não será atualizado.")
            elif data_hora_lembrete > agora:
                print(f"Lembrete futuro: '{lembrete['titulo']}' (ID: {lembrete['id']}) agendado para {lembrete['data']} às {lembrete['hora']}")
            else: # Já foi enviado em uma execução anterior
                print(f"Lembrete já enviado: '{lembrete['titulo']}' (ID: {lembrete['id']})")
        
        except ValueError as e:
            print(f"Erro no formato de data/hora do lembrete '{lembrete.get('titulo', 'N/A')}' (ID: {lembrete.get('id', 'N/A')}): {e}. Lembrete ignorado.")
        except Exception as e:
            print(f"Erro inesperado ao processar lembrete '{lembrete.get('titulo', 'N/A')}' (ID: {lembrete.get('id', 'N/A')}): {e}")
            
    # Salva o arquivo de lembretes APENAS se houver alteração (ou seja, se algum e-mail foi enviado)
    if lembretes_enviados_nesta_execucao > 0:
        salvar_lembretes_e_commitar(lembretes_atuais, f"Scheduler: Lembretes enviados ({lembretes_enviados_nesta_execucao}) atualizados.")
    else:
        print("Nenhum lembrete novo para enviar ou alterar status.")
        
    print(f"[{datetime.now(FUSO_HORARIO_BRASIL).strftime('%Y-%m-%d %H:%M:%S')}] Verificação concluída. {lembretes_enviados_nesta_execucao} lembrete(s) enviado(s) nesta execução.")

if __name__ == '__main__':
    main()