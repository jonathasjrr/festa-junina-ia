import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import pandas as pd
import re

# ==========================================
# CONFIGURAÇÃO DE SEGURANÇA
# ==========================================
if "GEMINI_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_KEY"])
else:
    st.error("Por favor, configure a chave GEMINI_KEY nos Secrets do Streamlit.")

# ==========================================
# DETECÇÃO AUTOMÁTICA DE MODELO
# ==========================================
@st.cache_resource
def obter_modelo_seguro():
    try:
        modelos_disponiveis = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                nome_limpo = m.name.replace('models/', '')
                modelos_disponiveis.append(nome_limpo)
        
        for modelo in modelos_disponiveis:
            if 'flash' in modelo.lower():
                return modelo
                
        if modelos_disponiveis:
            return modelos_disponiveis[0]
            
        return 'gemini-1.5-flash'
    except Exception as e:
        return 'gemini-1.5-flash'

MODELO_ATUAL = obter_modelo_seguro()

# ==========================================
# CONEXÃO DIRETA COM O GOOGLE SHEETS
# ==========================================
# COLE O SEU LINK COM O #GID AQUI:
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1ao4BKfUHK7C_jmuJUPwwXwhpy2e7IhVjdAId6QyAMrE/edit?gid=1055187794#gid=1055187794"

conn_sheets = st.connection("gsheets", type=GSheetsConnection)

def buscar_dados_planilha():
    df = conn_sheets.read(spreadsheet=URL_PLANILHA, ttl=5)
    return df

def atualizar_reserva_planilha(item_nome, pessoa_nome):
    df = buscar_dados_planilha()
    if df.empty:
        return False
    
    coluna_item = 'Nome_Item'
    coluna_responsavel = 'Quem_Vai_Trazer'
    
    if coluna_item not in df.columns or coluna_responsavel not in df.columns:
        return False

    df['Item_Lower'] = df[coluna_item].astype(str).str.lower().str.strip()
    item_procurado = item_nome.lower().strip()
    
    if item_procurado in df['Item_Lower'].values:
        idx = df[df['Item_Lower'] == item_procurado].index[0]
        df.at[idx, coluna_responsavel] = pessoa_nome
        df = df.drop(columns=['Item_Lower'])
        
        # CORREÇÃO AQUI: Comando correto para gravar os dados sem causar conflito
        conn_sheets.update(data=df)
        
        # Limpa a memória temporária do Streamlit para ele ler a planilha nova imediatamente
        st.cache_data.clear() 
        return True
    return False

def formatar_cardapio_para_ia(df):
    if df.empty:
        return "A planilha está vazia no momento."
        
    texto = "Lista atual de itens na nossa planilha:\n"
    coluna_item = 'Nome_Item'
    coluna_responsavel = 'Quem_Vai_Trazer'
    
    for _, row in df.iterrows():
        if pd.isna(row.get(coluna_item)):
            continue
            
        item = row[coluna_item]
        responsavel = row.get(coluna_responsavel, "em branco")
        
        if pd.isna(responsavel) or str(responsavel).strip().lower() in ["em branco", ""]:
            texto += f"- {item}: DISPONÍVEL\n"
        else:
            texto += f"- {item}: Já reservado por {responsavel}\n"
            
    return texto

# ==========================================
# INTERFACE VISUAL
# ==========================================
st.set_page_config(page_title="IA da nossa Festa Junina!", page_icon="🔥")

st.title("🤠 Assistente da nossa Festa Junina!")
st.write("Olá! Eu ajudo a organizar nosso Arraiá. Pergunte-me o que falta trazer ou envie o comprovante do Pix!")

st.sidebar.header("📍 Informações Importantes")
st.sidebar.write("**Endereço:** Rua das Bandeirinhas, nº 123 - Bairro Centro")
st.sidebar.write("**Horário:** Sábado, a partir das 18:00")
st.sidebar.write("**Chave Pix para colaborar:** pix@nossofestejo.com")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Ô de casa! Bão demais da conta? Pergunte-me o que já tem de comida na nossa planilha, o que ainda tá faltando ou me diga o seu nome e o que deseja trazer pra nossa festança!"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Digite sua pergunta aqui...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("Anotando no caderninho e falando com a IA..."):
        try:
            df_atual = buscar_dados_planilha()
            dados_festa = formatar_cardapio_para_ia(df_atual)
        except Exception as e:
            st.error(f"❌ ERRO DE PLANILHA: Detalhe: {e}")
            st.stop()

        try:
            modelo = genai.GenerativeModel(MODELO_ATUAL)
            
            prompt_sistema = f"""
            Você é um organizador de festa junina muito simpático, caipira, prestativo e paciente.
            O endereço da festa é: Rua das Bandeirinhas, nº 123 - Bairro Centro.
            O horário é: Sábado às 18:00.
            A chave pix é: pix@nossofestejo.com.
            
            Aqui estão os dados REAIS e EXATOS vindos diretamente da nossa planilha:
            {dados_festa}
            
            REGRAS OBRIGATÓRIAS DE COMPORTAMENTO:
            1. Use bastante o sotaque caipira e emojis caipiras (🌽🤠🔥).
            2. Se o usuário perguntar o que está faltando ou o que tem na lista, você deve listar TODOS os itens marcados como DISPONÍVEL que estão nos dados acima. É EXPRESSAMENTE PROIBIDO resumir, ocultar itens ou inventar opções que não estão nessa lista.
            3. Se o usuário disser que quer trazer um item que está marcado como DISPONÍVEL e disser o seu próprio nome, responda iniciando sua mensagem EXATAMENTE com a tag estruturada [RESERVA: NomeDoItem | NomeDaPessoa]. 
            4. CASO O USUÁRIO NÃO SE IDENTIFIQUE: Não use a tag de reserva! Peça o nome dele de maneira muito educada, divertida e carinhosa com sotaque caipira antes de poder confirmar.
            """
            
            prompt_completo_seguro = f"{prompt_sistema}\n\n[MENSAGEM DO USUÁRIO]: {user_input}"
            
            resposta_ia = modelo.generate_content(prompt_completo_seguro).text
            
            # Lógica corrigida para lidar com a reserva e APAGAR a tag da tela
            if "[RESERVA:" in resposta_ia:
                try:
                    # Extrai os nomes
                    texto_dentro_colchetes = resposta_ia.split("[RESERVA:")[1].split("]")[0]
                    partes = texto_dentro_colchetes.split("|")
                    item_reserva = partes[0].strip()
                    nome_reserva = partes[1].strip()
                    
                    # Tenta salvar na planilha
                    sucesso = atualizar_reserva_planilha(item_reserva, nome_reserva)
                    
                    # Limpa a tag feia da resposta (substitui por vazio)
                    resposta_ia = re.sub(r'\[RESERVA:.*?\]', '', resposta_ia).strip()
                    
                    if sucesso:
                        resposta_ia += f"\n\n✨ 🎉 Eita coisa boa! Já escrevi aqui na nossa planilha oficial que o(a) {nome_reserva} vai trazer {item_reserva}! Muito obrigado pela ajuda, sô!"
                    else:
                        resposta_ia += f"\n\nOpa, olhei aqui na planilha e não encontrei o prato '{item_reserva}' na nossa lista oficial. Cê escreveu igualzinho tá na lista?"
                except Exception as erro_reserva:
                    # SE DER ERRO NO SALVAMENTO, ELE VAI AVISAR AQUI:
                    st.error(f"❌ Erro crítico ao tentar gravar na planilha do Google: {erro_reserva}")
            
            st.session_state.messages.append({"role": "assistant", "content": resposta_ia})
            with st.chat_message("assistant"):
                st.write(resposta_ia)
                
        except Exception as e:
            st.error(f"🤖 ERRO DA IA: Não foi possível processar a mensagem. Detalhe: {e}")

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
            modelo_visao = genai.GenerativeModel(MODELO_ATUAL)
            prompt_ocr = "Analise esta imagem. Isto é um comprovante de Pix válido? Se sim, leia o documento e me devolva APENAS o nome de quem pagou e o valor no formato: 'Nome da Pessoa - R$ Valor'. Se não for um comprovante Pix, diga apenas 'Inválido'."
            
            resultado = modelo_visao.generate_content([prompt_ocr, imagem]).text
            
            if "Inválido" not in resultado:
                st.success(f"Obrigado! Comprovante recebido: {resultado}")
            else:
                st.error("Não consegui identificar este arquivo como um comprovante de Pix. Pode enviar novamente?")
        except Exception as e:
            st.error(f"Erro ao processar o comprovante: {e}")
