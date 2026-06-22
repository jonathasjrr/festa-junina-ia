import streamlit as st
import sqlite3
import google.generativeai as genai
from PIL import Image
import requests

# ==========================================
# BANCO DE DADOS LOCAL NA NUVEM (SQLite)
# ==========================================
conn = sqlite3.connect('festajunina.db', check_same_thread=False)
c = conn.cursor()

# Cria as tabelas se não existirem
c.execute('''
    CREATE TABLE IF NOT EXISTS cardapio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT,
        categoria TEXT,
        responsavel TEXT,
        status TEXT
    )
''')
conn.commit()

# Adiciona alguns itens iniciais de teste se a tabela estiver vazia
c.execute("SELECT COUNT(*) FROM cardapio")
if c.fetchone()[0] == 0:
    itens_iniciais = [
        ('Bolo de Milho', 'Doce', 'Pendente', 'Pendente'),
        ('Canjica', 'Doce', 'Pendente', 'Pendente'),
        ('Pipoca', 'Salgado', 'Pendente', 'Pendente'),
        ('Pastel', 'Salgado', 'Pendente', 'Pendente'),
        ('Quentão', 'Bebida', 'Pendente', 'Pendente')
    ]
    c.executemany("INSERT INTO cardapio (item, categoria, responsavel, status) VALUES (?, ?, ?, ?)", itens_iniciais)
    conn.commit()

def buscar_estado_festa():
    c.execute("SELECT item, categoria, responsavel, status FROM cardapio")
    linhas = c.fetchall()
    texto = "Lista de comidas e quem vai trazer:\n"
    for l in linhas:
        texto += f"- {l[0]} ({l[1]}): "
        if l[3] == 'Confirmado':
            texto += f"Confirmado por {l[2]}\n"
        else:
            texto += "Ainda ninguém vai trazer (Está disponível!)\n"
    return texto

def reservar_item(item_nome, pessoa_nome):
    c.execute("UPDATE cardapio SET responsavel=?, status='Confirmado' WHERE LOWER(item)=LOWER(?)", (pessoa_nome, item_nome.strip()))
    conn.commit()
    return c.rowcount > 0

# ==========================================
# CONFIGURAÇÃO DE SEGURANÇA (Chaves secretas)
# ==========================================
# O Streamlit permite esconder as chaves em uma área segura do servidor
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("Por favor, configure a chave GEMINI_KEY nos Secrets do Streamlit.")

# ==========================================
# INTERFACE VISUAL (Amigável para idosos)
# ==========================================
st.set_page_config(page_title="IA da nossa Festa Junina!", page_icon="🔥")

st.title("🤠 Assistente da nossa Festa Junina!")
st.write("Olá! Eu sou o assistente virtual da festa. Você pode falar comigo por texto ou me mandar uma foto do comprovante do Pix aqui embaixo.")

# Informações fixas na barra lateral para facilitar leitura
st.sidebar.header("📍 Informações Importantes")
st.sidebar.write("**Endereço:** Rua das Bandeirinhas, nº 123 - Bairro Centro")
st.sidebar.write("**Horário:** Sábado, a partir das 18:00")
st.sidebar.write("**Chave Pix para colaborar:** pix@nossofestejo.com")

# Histórico de Conversa do Chat
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Olá! Pergunte-me o que já tem de comida, o que falta trazer, confirme o endereço ou me diga se você vai trazer algum prato!"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Entrada de texto da IA
user_input = st.chat_input("Digite sua pergunta aqui...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # Processamento com o Gemini
    with st.spinner("Pensando..."):
        try:
            modelo = genai.GenerativeModel('gemini-1.5-flash')
            
            # Buscando os dados em tempo real do banco de dados
            dados_festa = buscar_estado_festa()
            
            prompt_sistema = f"""
            Você é um organizador de festa junina muito simpático, prestativo e paciente, focado em ajudar pessoas idosas.
            O endereço da festa é: Rua das Bandeirinhas, nº 123 - Bairro Centro.
            O horário é: Sábado às 18:00.
            A chave pix é: pix@nossofestejo.com.
            
            Aqui está o estado atual do cardápio do nosso banco de dados:
            {dados_festa}
            
            Responda de forma clara, curta e carinhosa. Use emojis caipiras.
            Se o usuário disser explicitamente que quer trazer um item que está DISPONÍVEL (ex: "Quero levar Canjica" ou "Vou levar Canjica" e meu nome é "João"), responda iniciando sua mensagem EXATAMENTE com a tag [RESERVA: NomeDoItem | NomeDaPessoa]. Se não tiver o nome da pessoa, peça o nome dela educadamente antes de confirmar.
            """
            
            resposta_ia = modelo.generate_content([prompt_sistema, user_input]).text
            
            # Lógica para atualizar o banco de dados caso a IA detecte uma intenção de reserva
            if "[RESERVA:" in resposta_ia:
                try:
                    # Extrai os dados da tag secreta da IA
                    partes = resposta_ia.split("[RESERVA:")[1].split("]")[0].split("|")
                    item_reserva = partes[0].strip()
                    nome_reserva = partes[1].strip()
                    
                    sucesso = reservar_item(item_reserva, nome_reserva)
                    # Remove a tag estruturada do texto final para o convidado não ver código feio
                    resposta_ia = resposta_ia.split("[RESERVA:")[0] + f"\n\n✨ Perfeito! Já anotei aqui no meu caderninho que o(a) {nome_reserva} vai trazer {item_reserva}! 🎉"
                except:
                    pass
            
            st.session_state.messages.append({"role": "assistant", "content": resposta_ia})
            with st.chat_message("assistant"):
                st.write(resposta_ia)
        except Exception as e:
       st.error(f"Erro detalhado: {e}")

# ==========================================
# SESSÃO DE UPLOAD DO PIX
# ==========================================
st.markdown("---")
st.subheader("📸 Enviou um Pix? Mande o comprovante aqui:")
arquivo_foto = st.file_uploader("Clique no botão abaixo para tirar uma foto ou escolher o comprovante", type=['png', 'jpg', 'jpeg'])

if arquivo_foto:
    imagem = Image.open(arquivo_foto)
    st.image(imagem, caption="Comprovante carregado pelo celular.", width=250)
    
    with st.spinner('Lendo o comprovante...'):
        try:
            modelo_visao = genai.GenerativeModel('gemini-1.5-flash')
            prompt_ocr = "Analise esta imagem. Isto é um comprovante de Pix válido? Se sim, leia o documento e me devolva APENAS o nome de quem pagou e o valor no formato: 'Nome da Pessoa - R$ Valor'. Se não for um comprovante Pix, diga apenas 'Inválido'."
            
            resultado = modelo_visao.generate_content([prompt_ocr, image]).text
            
            if "Inválido" not in resultado:
                st.success(f"Obrigado! Comprovante recebido: {resultado}")
                
                # Envia notificação secreta para o seu Telegram
                if "TELEGRAM_TOKEN" in st.secrets and "TELEGRAM_CHAT_ID" in st.secrets:
                    token = st.secrets["TELEGRAM_TOKEN"]
                    chat_id = st.secrets["TELEGRAM_CHAT_ID"]
                    msg_telegram = f"🔔 *Alerta de Pix Junino!*\n{resultado}"
                    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": msg_telegram, "parse_mode": "Markdown"})
            else:
                st.error("Não consegui identificar este arquivo como um comprovante de Pix. Pode enviar novamente?")
        except Exception as e:
            st.error("Erro ao processar a imagem do comprovante.")
