import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- Configurações para Armazenamento e E-mail ---
# Os caminhos são relativos ao diretório raiz do repositório no GitHub Actions
LEMBRETES_FILE = 'lembretes.json'
CONFIG_FILE = 'config.json'

# Credenciais de e-mail (serão lidas das variáveis de ambiente do GitHub Actions)
EMAIL_REMETENTE_USER = os.getenv("GMAIL_USER")
EMAIL_REMETENTE_PASS = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_ADMIN_FALLBACK = os.getenv("EMAIL_ADMIN", EMAIL_REMETENTE_USER)

# --- Funções de Carregamento/Salvamento ---
def carregar_lembretes():
    if not os.path.exists(LEMBRETES_FILE):
        return [] # Retorna vazio se não existir
    try:
        with open(LEMBRETES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Aviso: O arquivo '{LEMBRETES_FILE}' está vazio ou corrompido. Retornando lista vazia.")
        return []

def salvar_lembretes(lembretes):
    with open(LEMBRETES_FILE, 'w', encoding='utf-8') as f:
        json.dump(lembretes, f, indent=4, ensure_ascii=False)
    print(f"Status de lembretes salvo em '{LEMBRETES_FILE}'.")


def carregar_configuracoes():
    if not os.path.exists(CONFIG_FILE):
        return {"email_destino": EMAIL_ADMIN_FALLBACK}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            if "email_destino" not in config:
                config["email_destino"] = EMAIL_ADMIN_FALLBACK
            return config
    except json.JSONDecodeError:
        print(f"Aviso: O arquivo '{CONFIG_FILE}' está vazio ou corrompido. Retornando configurações padrão.")
        return {"email_destino": EMAIL_ADMIN_FALLBACK}

# --- Funções de E-mail ---
def enviar_email(destinatario, assunto, corpo):
    if not EMAIL_REMETENTE_USER or not EMAIL_REMETENTE_PASS:
        print("Erro: Credenciais de e-mail do remetente (GMAIL_USER ou GMAIL_APP_PASSWORD) não configuradas nas secrets do GitHub.")
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
        print(f"Lembrete enviado com sucesso para {destinatario}: '{assunto}'")
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail para {destinatario}: {e}")
        return False

# --- Lógica principal de verificação e envio ---
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando verificação de lembretes...")
    lembretes = carregar_lembretes()
    config = carregar_configuracoes()
    email_destino_lembretes = config.get("email_destino", EMAIL_ADMIN_FALLBACK)
    
    if not email_destino_lembretes or not (EMAIL_REMETENTE_USER and EMAIL_REMETENTE_PASS):
        print("Aviso: E-mail de destino ou credenciais do remetente não configurados. Não será possível enviar e-mails.")
        return

    agora = datetime.now()
    lembretes_atualizados = []
    lembretes_enviados_nesta_execucao = 0

    for lembrete in lembretes:
        try:
            # Garante que 'data' e 'hora' são strings antes de concatenar
            lembrete_data_str = str(lembrete.get('data', ''))
            lembrete_hora_str = str(lembrete.get('hora', ''))

            # Adiciona validação básica para formatos esperados
            if not lembrete_data_str or not lembrete_hora_str:
                print(f"Aviso: Lembrete '{lembrete.get('titulo', 'N/A')}' tem data/hora inválida ou ausente. Ignorando.")
                lembretes_atualizados.append(lembrete)
                continue

            data_hora_lembrete = datetime.strptime(f"{lembrete_data_str} {lembrete_hora_str}", "%Y-%m-%d %H:%M")
            
            if data_hora_lembrete <= agora and not lembrete.get('enviado', False):
                assunto = f"Lembrete: {lembrete['titulo']}"
                corpo = f"Olá!\n\nVocê tem um lembrete pendente:\n\nTítulo: {lembrete['titulo']}\nDescrição: {lembrete['descricao']}\nData: {lembrete['data']}\nHora: {lembrete['hora']}\n\nNão se esqueça!"
                
                print(f"Processando lembrete para envio: '{lembrete['titulo']}' (ID: {lembrete['id']})")
                if enviar_email(email_destino_lembretes, assunto, corpo):
                    lembrete['enviado'] = True
                    lembretes_enviados_nesta_execucao += 1
                else:
                    print(f"Falha ao enviar lembrete: '{lembrete['titulo']}'.")
            elif data_hora_lembrete > agora:
                print(f"Lembrete futuro: '{lembrete['titulo']}' (ID: {lembrete['id']}) em {lembrete['data']} às {lembrete['hora']}")
            else: # Já foi enviado
                print(f"Lembrete já enviado: '{lembrete['titulo']}' (ID: {lembrete['id']})")
        except ValueError as e:
            print(f"Erro no formato de data/hora do lembrete '{lembrete.get('titulo', 'N/A')}': {e}. Lembrete ignorado.")
        except Exception as e:
            print(f"Erro inesperado ao processar lembrete '{lembrete.get('titulo', 'N/A')}': {e}")
            
        lembretes_atualizados.append(lembrete)

    salvar_lembretes(lembretes_atualizados) # Salva o status 'enviado' no JSON no repositório do Actions
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Verificação concluída. {lembretes_enviados_nesta_execucao} lembrete(s) enviado(s) nesta execução.")

if __name__ == '__main__':
    main()