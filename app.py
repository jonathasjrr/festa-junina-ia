import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import requests
import pandas as pd

# ==========================================
# CONFIGURAÇÃO DE SEGURANÇA (Chaves secretas)
# ==========================================
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("Por favor, configure a chave GEMINI_KEY nos Secrets do Streamlit.")

# ==========================================
# CONEXÃO DIRETA COM O GOOGLE SHEETS
# ==========================================
# Link da sua planilha do Google Sheets
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1ao4BKfUHK7C_jmuJUPwwXwhpy2e7IhVjdAId6QyAMrE/edit?usp=sharing"

# Inicializa a conexão do Streamlit com o Google Sheets
conn_sheets = st.connection("gsheets", type=GSheetsConnection)

def buscar_dados_planilha():
    # Lê a planilha atualizada em tempo real
    df = conn_sheets.read(spreadsheet=URL_PLANILHA, ttl=5) # ttl=5 limpa o cache a cada 5 segundos
    return df

def atualizar_reserva_planilha(item_nome, pessoa_nome):
    df = buscar_dados_planilha()
    if df.empty:
        return False
    
    colunas = df.columns.tolist()
    # Assume que a 1ª coluna é sempre o item (Comida/Prato)
    coluna_item = colunas[0] 
    
    # Tenta descobrir dinamicamente quais são as colunas de Responsável e Status
    coluna_responsavel = next((c for c in colunas if any(x in c.lower() for x in ['respons', 'nome', 'quem', 'pessoa'])), colunas[1] if len(colunas) > 1 else None)
    coluna_status = next((c for c in colunas if any(x in c.lower() for x in ['status', 'situa', 'estado'])), colunas[2] if len(colunas) > 2 else None)
    
    # Converte para minúsculo para evitar problemas de digitação
    df['Item_Lower'] = df[coluna_item].astype(str).str.lower().str.strip()
    item_procurado = item_nome.lower().strip()
    
    if item_procurado in df['Item_Lower'].values:
        # Encontra a linha correspondente e atualiza as informações
        idx = df[df['Item_Lower'] == item_procurado].index[0]
        
        if coluna_responsavel:
            df.at[idx, coluna_responsavel] = pessoa_nome
        if coluna_status:
            df.at[idx, coluna_status] = 'Confirmado'
        
        # Remove a coluna temporária antes de salvar de volta
        df = df.drop(columns=['Item_Lower'])
        
        # Grava as alterações diretamente de volta no Google Sheets
        conn_sheets.update(spreadsheet=URL_PLANILHA, data=df)
        return True
    return False

def formatar_cardapio_para_ia(df):
    if df.empty:
        return "A planilha está vazia no momento."
        
    texto = "Lista atual da nossa planilha:\n"
    colunas = df.columns.tolist()
    
    for _, row in df.iterrows():
        detalhes = []
        for col in colunas:
            valor = row[col] if pd.notna(row[col]) else "Vazio"
            detalhes.append(f"{col}: {valor}")
        texto += "- " + " | ".join(detalhes) + "\n"
    return texto

# ==========================================
# INTERFACE VISUAL (Amigável para idosos)
# ==========================================
st.set_page_config(page_title="IA da nossa Festa Junina!", page_icon="🔥")

st.title("🤠 Assistente da nossa Festa Junina!")
st.write("Olá! Eu ajudo a organizar nosso Arraiá. Pergunte-me o que falta trazer ou envie o comprovante do Pix!")

# Informações fixas na lateral
st.sidebar.header("📍 Informações Importantes")
st.sidebar.write("**Endereço:** Rua das Bandeirinhas, nº 123 - Bairro Centro")
st.sidebar.write("**Horário:** Sábado, a partir das 18:00")
st.sidebar.write("**Chave Pix para colaborar:** pix@nossofestejo.com")

# Histórico de Conversa do Chat
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Ô de casa! Bão demais da conta? Pergunte-me o que já tem de comida na nossa planilha, o que ainda tá faltando ou me diga o seu nome e o que deseja trazer pra nossa festança!"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Entrada de texto da IA
user_input = st.chat_input("Digite sua pergunta aqui...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("Espiando na planilha..."):
        try:
            modelo = genai.GenerativeModel('gemini-1.5-flash')
            
            # 1. Busca os dados reais direto da planilha
            df_atual = buscar_dados_planilha()
            dados_festa = formatar_cardapio_para_ia(df_atual)
            
            prompt_sistema = f"""
            Você é um organizador de festa junina muito simpático, caipira, prestativo e paciente, focado em ajudar pessoas idosas da família.
            O endereço da festa é: Rua das Bandeirinhas, nº 123 - Bairro Centro.
            O horário é: Sábado às 18:00.
            A chave pix é: pix@nossofestejo.com.
            
            Aqui estão os dados REAIS vindos da nossa planilha do Google Sheets, com os campos exatos que estão lá:
            {dados_festa}
            
            Responda de forma clara, curta e bem acolhedora. Use bastante o sotaque caipira e emojis (🌽🤠🔥).
            Se o usuário disser explicitamente que quer trazer um item que parece estar disponível e falar o nome dele, responda iniciando sua mensagem EXATAMENTE com a tag estruturada [RESERVA: NomeDoItem | NomeDaPessoa]. 
            
            ⚠️ IMPORTANTE: Se ele disser o que quer levar, mas esquecer de dizer o nome dele, NÃO inicie com a tag de RESERVA. Em vez disso, peça o nome dele de maneira MUITO educada, divertida e com sotaque caipira (ex: "Opa, cumpadi/cumadi! Bão demais que cê vai trazer isso! Mas pra eu anotar aqui no meu caderninho, cê precisa me dizê seu nome, sô!").
            """
            
            resposta_ia = modelo.generate_content([prompt_sistema, user_input]).text
            
            # 2. Se a IA gerou o comando de reserva, atualizamos a planilha
            if "[RESERVA:" in resposta_ia:
                try:
                    partes = resposta_ia.split("[RESERVA:")[1].split("]")[0].split("|")
                    item_reserva = partes[0].strip()
                    nome_reserva = partes[1].strip()
                    
                    sucesso = atualizar_reserva_planilha(item_reserva, nome_reserva)
                    
                    resposta_ia = resposta_ia.split("[RESERVA:")[0]
                    if sucesso:
                        resposta_ia += f"\n\n✨ 🎉 Eita coisa boa! Já escrevi aqui na nossa planilha oficial que o(a) {nome_reserva} vai trazer {item_reserva}! Muito obrigado pela ajuda, sô!"
                    else:
                        resposta_ia += f"\n\nOpa, olhei aqui na planilha e não encontrei o prato '{item_reserva}' na nossa lista. Cê pode conferir se digitou o nome certinho igual tá lá?"
                except Exception as erro_reserva:
                    pass
            
            st.session_state.messages.append({"role": "assistant", "content": resposta_ia})
            with st.chat_message("assistant"):
                st.write(resposta_ia)
        except Exception as e:
            st.error(f"Erro detalhado ao processar o chat: {e}")

# ==========================================
# SESSÃO DE UPLOAD DO PIX
# ==========================================
st.markdown("---")
st.subheader("📸 Enviou um Pix? Mande o comprovante aqui:")
arquivo_foto = st.file_uploader("Clique abaixo para tirar foto ou escolher o arquivo", type=['png', 'jpg', 'jpeg'])

if arquivo_foto:
    imagem = Image.open(arquivo_foto)
    st.image(imagem, caption="Comprovante carregado.", width=250)
    
    with st.spinner('Lendo o comprovante...'):
        try:
            modelo_visao = genai.GenerativeModel('gemini-1.5-flash')
            prompt_ocr = "Analise esta imagem. Isto é um comprovante de Pix válido? Se sim, leia o documento e me devolva APENAS o nome de quem pagou e o valor no formato: 'Nome da Pessoa - R$ Valor'. Se não for um comprovante Pix, diga apenas 'Inválido'."
            
            resultado = modelo_visao.generate_content([prompt_ocr, imagem]).text
            
            if "Inválido" not in resultado:
                st.success(f"Obrigado! Comprovante recebido: {resultado}")
                
                if "TELEGRAM_TOKEN" in st.secrets and "TELEGRAM_CHAT_ID" in st.secrets:
                    token = st.secrets["TELEGRAM_TOKEN"]
                    chat_id = st.secrets["TELEGRAM_CHAT_ID"]
                    msg_telegram = f"🔔 *Alerta de Pix Junino!*\n{resultado}"
                    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat_id, "text": msg_telegram, "parse_mode": "Markdown"})
            else:
                st.error("Não consegui identificar este arquivo como um comprovante de Pix. Pode enviar novamente?")
        except Exception as e:
            st.error(f"Erro ao processar o comprovante: {e}")
