import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import requests
import os
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
                modelos_disponiveis.append(m.name.replace('models/', ''))
        for modelo in modelos_disponiveis:
            if 'flash' in modelo.lower():
                return modelo
        if modelos_disponiveis: return modelos_disponiveis[0]
        return 'gemini-1.5-flash'
    except Exception:
        return 'gemini-1.5-flash'

MODELO_ATUAL = obter_modelo_seguro()

# ==========================================
# BANCO DE DADOS INTERNO E LÓGICA
# ==========================================
ARQUIVO_DADOS = "dados_arraia.csv"

ITENS_PADRAO = [
    "Quentão", "Salsichão (30 u)", "Bolo de Cenoura", "Bolo de Aipim", "Cocada",
    "Pé de Moleque", "Doce de Amendoim", "Paçoca", "Cuscuz de Tapioca", "Caldo Verde",
    "Sopa de Ervilha", "Espetinho de Churrasco (30 u)", "Torta Salgada", "Curau",
    "Arroz Doce", "Salgadinho (100u)", "Cachorro quente (Pão e Molho)", 
    "Milho cozido (25 u)", "Caldo de Kenga", "Doce de Leite", "Salada de Fruta"
]

def enviar_aviso_telegram(mensagem):
    if "TELEGRAM_TOKEN" in st.secrets and "TELEGRAM_CHAT_ID" in st.secrets:
        try:
            token = st.secrets["TELEGRAM_TOKEN"]
            chat_id = st.secrets["TELEGRAM_CHAT_ID"]
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage", 
                data={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
            )
        except Exception:
            pass

def carregar_dados():
    if not os.path.exists(ARQUIVO_DADOS):
        df = pd.DataFrame({"Nome_Item": ITENS_PADRAO, "Quem_Vai_Trazer": ["em branco"] * len(ITENS_PADRAO)})
        df.to_csv(ARQUIVO_DADOS, index=False)
        return df
    return pd.read_csv(ARQUIVO_DADOS)

def adicionar_novo_item_lista(nome_item):
    """Insere uma nova opção de comida sugerida pelo usuário no banco de dados"""
    df = carregar_dados()
    nome_item_limpo = nome_item.strip()
    
    # Verifica se já existe um item com o mesmo nome (ignorando maiúsculas/minúsculas)
    if nome_item_limpo.lower() in df['Nome_Item'].astype(str).str.lower().str.strip().values:
        return False
        
    novo_registro = pd.DataFrame({"Nome_Item": [nome_item_limpo], "Quem_Vai_Trazer": ["em branco"]})
    df = pd.concat([df, novo_registro], ignore_index=True)
    df.to_csv(ARQUIVO_DADOS, index=False)
    
    enviar_aviso_telegram(f"➕ *NOVA OPÇÃO NO CARDÁPIO!*\nAlguém adicionou um novo item à lista: *{nome_item_limpo}*")
    return True

def atualizar_reserva_local(item_nome, pessoa_nome):
    df = carregar_dados()
    item_nome_limpo = item_nome.replace("*", "").replace("_", "").strip().lower()
    df['Item_Lower'] = df['Nome_Item'].astype(str).str.lower().str.strip()
    
    df_disponiveis = df[df['Quem_Vai_Trazer'].astype(str).str.strip().str.lower().isin(['em branco', '', 'nan'])]
    match = df_disponiveis[df_disponiveis['Item_Lower'].str.contains(item_nome_limpo, na=False, regex=False)]
    
    if not match.empty:
        idx = match.index[0] 
        item_real = df.at[idx, 'Nome_Item']
        df.at[idx, 'Quem_Vai_Trazer'] = pessoa_nome
        df = df.drop(columns=['Item_Lower'])
        df.to_csv(ARQUIVO_DADOS, index=False) 
        
        enviar_aviso_telegram(f"🌽 *NOVA RESERVA DO ARRAIÁ!*\nO(a) {pessoa_nome} reservou: *{item_real}*")
        return True
    return False

def formatar_cardapio_para_ia():
    df = carregar_dados()
    texto = "Lista atual da nossa festa:\n"
    for _, row in df.iterrows():
        item = row['Nome_Item']
        responsavel = str(row['Quem_Vai_Trazer'])
        
        if pd.isna(responsavel) or responsavel.strip().lower() in ["em branco", ""]:
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

# Painel Lateral de Informações
st.sidebar.header("📍 Informações Importantes")
st.sidebar.write("**Endereço:** Rua Francisca Constantina, nº 137 - Bairro Porto Novo/SG")
st.sidebar.write("**Data:** 18 de Julho de 2026")
st.sidebar.write("**Horário:** Sábado, a partir das 19:00")
st.sidebar.write("**Pensamos em alugar uma Sinuca e Totó, quer nos ajudar?** Chave pix: jonathasjrr@gmail.com")

# --- NOVA FUNCIONALIDADE: FORMULÁRIO PARA ADICIONAR ITENS ---
st.sidebar.markdown("---")
st.sidebar.subheader("➕ Sugerir Nova Comida/Bebida")
comida_sugerida = st.sidebar.text_input("O que deseja adicionar?", placeholder="Ex: Bolo de Fubá, Pipoca Doce...", key="nova_comida")

if st.sidebar.button("Adicionar à Lista de Opções"):
    if comida_sugerida.strip():
        sucesso_add = adicionar_novo_item_lista(comida_sugerida)
        if sucesso_add:
            st.sidebar.success(f"🎉 '{comida_sugerida}' agora faz parte das opções!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.warning("Uai, esse item já tá na nossa lista de opções!")
    else:
        st.sidebar.error("Por favor, digite o nome de alguma coisa antes de clicar!")

# Exibição do Painel da Lista Geral
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Lista Atualizada")
st.sidebar.dataframe(carregar_dados(), hide_index=True)

# Histórico do Chat
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Ô de casa! Bão demais da conta? Pergunte-me o que já tem de comida na nossa listinha, o que ainda tá faltando ou me diga o seu nome e o que deseja trazer pra nossa festança!"}]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Digite sua pergunta aqui...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.spinner("Processando histórico e falando com a IA..."):
        try:
            dados_festa = formatar_cardapio_para_ia()
            modelo = genai.GenerativeModel(MODELO_ATUAL)
            
            historico_conversa = ""
            for msg in st.session_state.messages:
                papel = "Usuário" if msg["role"] == "user" else "Organizador (Você)"
                historico_conversa += f"{papel}: {msg['content']}\n"
            
            prompt_sistema = f"""
            Você é um organizador de festa junina muito simpático, caipira, prestativo e paciente.
            O endereço da festa é: Rua das Bandeirinhas, nº 123 - Bairro Centro.
            O horário é: Sábado às 18:00.
            
            Aqui estão os dados REAIS e EXATOS vindos diretamente da nossa lista atualizada:
            {dados_festa}
            
            REGRAS OBRIGATÓRIAS DE COMPORTAMENTO:
            1. Use bastante o sotaque caipira e emojis caipiras (🌽🤠🔥).
            2. Se o usuário perguntar o que está faltando, liste TODOS os itens marcados como DISPONÍVEL. NÃO RESUMA e NÃO INVENTE itens.
            3. Se no histórico de conversa abaixo o usuário demonstrar intenção de trazer um item disponível E você já souber (ou ele acabar de fornecer) o nome dele, você deve responder iniciando sua mensagem EXATAMENTE com a tag estruturada [RESERVA: NomeDoItem | NomeDaPessoa].
            4. CASO O USUÁRIO NÃO SE IDENTIFIQUE AINDA: Não use a tag de reserva. Peça o nome dele de maneira muito educada e com sotaque caipira antes de poder confirmar. Se o usuário disser que quer trazer algo que não está listado nos dados reais, avise-o amigavelmente que ele pode usar o campo na lateral da tela para adicionar essa opção primeiro!
            
            [HISTÓRICO DA CONVERSA COMPLETA]:
            {historico_conversa}
            
            Analise o histórico acima completo para responder à última linha mantendo o contexto.
            """
            
            resposta_ia = modelo.generate_content(prompt_sistema).text
            precisa_recarregar = False
            
            if "[RESERVA:" in resposta_ia:
                try:
                    match_tag = re.search(r'\[RESERVA:(.*?)\]', resposta_ia)
                    if match_tag:
                        texto_dentro_colchetes = match_tag.group(1)
                        partes = texto_dentro_colchetes.split("|")
                        item_reserva = partes[0].replace("*", "").strip()
                        nome_reserva = partes[1].replace("*", "").strip()
                        
                        sucesso = atualizar_reserva_local(item_reserva, nome_reserva)
                        resposta_ia = re.sub(r'\[RESERVA:.*?\]', '', resposta_ia).strip()
                        
                        if sucesso:
                            resposta_ia += f"\n\n✨ 🎉 Eita coisa boa! Já escrevi aqui na nossa lista oficial que o(a) {nome_reserva} vai trazer {item_reserva}! Muito obrigado pela ajuda, sô!"
                            precisa_recarregar = True 
                        else:
                            resposta_ia += f"\n\nOpa, procurei aqui na lista e não achei o prato '{item_reserva}' livre ou válido. Cê escreveu igualzinho tá na lista?"
                except Exception as erro_reserva:
                    st.error(f"❌ Erro ao gravar internamente: {erro_reserva}")
            
            st.session_state.messages.append({"role": "assistant", "content": resposta_ia})
            
            if precisa_recarregar:
                st.rerun()
            else:
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
                enviar_aviso_telegram(f"🔔 *PIX JUNINO RECEBIDO!*\n{resultado}")
            else:
                st.error("Não consegui identificar este arquivo como um comprovante de Pix.")
        except Exception as e:
            st.error(f"Erro ao processar o comprovante: {e}")
