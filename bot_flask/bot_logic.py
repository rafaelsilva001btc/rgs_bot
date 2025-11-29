import threading
import time
import pandas as pd
from datetime import datetime
from binance.client import Client
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import os # Para ler variáveis de ambiente
import requests # Para fazer a requisição à API do Telegram

# =========================
# Configurações & Inicialização do Cliente
# =========================
# NOTA CRUCIAL: Inicializamos o Cliente sem API_KEY e API_SECRET,
# pois ele só está acessando endpoints públicos (klines, ticker).
client = Client()

# Configuração do Telegram (Lê variáveis de ambiente do Render)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# =========================
# Variáveis globais
# =========================
rodando = False
Posicao = False
SIMU_SALDO = 100.0
SIMU_QNT_MOEDA = 0.0
SIMU_LUCRO_VENDA = 0.0
Cotacao = 0.0
SIMU_PRECO_COMPRA = 0.0 # NOVO: Armazena o preço de entrada para P&L
GANHO_COUNT = 0         # NOVO: Contador de trades ganhadores
PERDA_COUNT = 0         # NOVO: Contador de trades perdedores

# Parâmetros padrão
params = {
    "symbol": "BTCUSDT",
    "mode": "SIMULADO",
    "estrategia": "RSI + Médias",
    "val_entrada": 10,
    "prsi": 9,
    "ind_SMA": 9,
    "ind_EMA": 6,
    "tempo_grafico": "1m",
    "limite_kendos": 50,
    "stop_gain": 2,
    "stop_loss": 2
}

# =========================
# Funções auxiliares de LOG
# =========================
def enviar_telegram(msg):
    """Envia a mensagem para o Telegram se as credenciais estiverem configuradas."""
    if TELEGRAM_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown" # Permite negrito, itálico, etc.
        }
        try:
            # Envia a requisição POST com um timeout
            requests.post(url, data=payload, timeout=10) 
        except Exception as e:
            print(f"[ERRO TELEGRAM] Falha ao enviar mensagem: {e}")

def enviar_log_geral(msg):
    """Função para logs gerais (início, parada, erros). Imprime no console e envia ao Telegram."""
    log_msg = f"[LOG] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}"
    print(log_msg)
    enviar_telegram(log_msg)

def log_compra(symbol, preco, saldo_antes, Valor_entrada, total_moeda):
    """Log estruturado para operações de compra."""
    msg = (
        f"🟢 *COMPRA EXECUTADA*\n"
        f"Moeda: *{symbol}*\n"
        f"Preço de Compra: *{preco:.2f} USD*\n"
        f"Valor de entrada: *{Valor_entrada:.2f} USD*\n"
        f"Saldo (Pós-Compra): *{saldo_antes:.4f} USD*\n"
        f"Total Moeda (Posição): *{total_moeda:.8f}*\n"
        f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    enviar_telegram(msg)

def log_venda(symbol, preco_venda, lucro_abs, saldo_final, Qnt_trade, resultado, ganho_count, perda_count):
    """Log estruturado para operações de venda."""
    msg = (
        f"🔴 *VENDA EXECUTADA ({resultado})*\n"
        f"Moeda: *{symbol}*\n"
        f"Preço de Venda: *{preco_venda:.2f} USD*\n"
        f"Lucro/Prejuízo: *{lucro_abs:+.6f} USD*\n" # Sinal + ou - no valor
        f"Saldo Total (Pós-Venda): *{saldo_final:.6f} USD*\n"
        f"Qnt Moeda Vendida: *{Qnt_trade:.8f}*\n"
        f"Trades Ganhos: *{ganho_count}* / Trades Perdidos: *{perda_count}*\n"
        f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    enviar_telegram(msg)

# =========================
# Funções auxiliares
# =========================
def get_price(symbol="BTCUSDT"):
    """Busca a cotação atual usando a API pública (sem autenticação)."""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        enviar_log_geral(f"Erro ao buscar preço: {e}")
        return 0.0

def calcular_indicadores(df, rsi_periodo, sma_periodo, ema_periodo):
    """Calcula RSI, EMA1 e EMA para o DataFrame."""
    # RSI
    rsi = RSIIndicator(close=df['close'], window=rsi_periodo)
    df['RSI'] = rsi.rsi()
    # EMA1 (usando o período do SMA para consistência)
    ema1 = EMAIndicator(close=df['close'], window=sma_periodo)
    df['EMA1'] = ema1.ema_indicator()
    # EMA
    ema = EMAIndicator(close=df['close'], window=ema_periodo)
    df['EMA'] = ema.ema_indicator()
    return df

# =========================
# Função principal de simulação
# =========================
def operacao_simulada():
    """Executa a lógica de simulação e trading."""
    global SIMU_SALDO, Posicao, SIMU_QNT_MOEDA, SIMU_LUCRO_VENDA, Cotacao
    global SIMU_PRECO_COMPRA, GANHO_COUNT, PERDA_COUNT
    
    try:
        # 1. Busca os Klines (Dados Históricos)
        klines = client.get_klines(
            symbol=params['symbol'], 
            interval=params['tempo_grafico'], 
            limit=params['limite_kendos']
        )
        
        # 2. Converte para DataFrame
        df = pd.DataFrame(klines, columns=[
            'time','open','high','low','close','volume','close_time','qav','trades','taker_base','taker_quote','ignore'
        ])
        df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
        
        # 3. Executa a Estratégia
        if params['estrategia'] == "RSI + Médias" and rodando:
            df = calcular_indicadores(df, params['prsi'], params['ind_SMA'], params['ind_EMA'])
            
            # Pega os últimos valores
            ultimo_rsi = df['RSI'].iloc[-1]
            ultima_sma = df['EMA1'].iloc[-1]
            ultima_ema = df['EMA'].iloc[-1]
            Cotacao = df['close'].iloc[-1]

            # Lógica de Compra simulada
            if ultimo_rsi < 50 and ultima_ema > ultima_sma and not Posicao:
                valor_entrada = SIMU_SALDO * params['val_entrada'] / 100
                SIMU_QNT_MOEDA = round(valor_entrada / Cotacao, 8)
                SIMU_SALDO -= valor_entrada
                SIMU_PRECO_COMPRA = Cotacao # NOVO: Armazena o preço de compra
                Posicao = True
                
                # CHAMA NOVO LOG DE COMPRA
                log_compra(
                    params['symbol'], 
                    Cotacao, 
                    SIMU_SALDO, 
                    valor_entrada, 
                    SIMU_QNT_MOEDA
                )

            # Lógica de Venda simulada com Stop Gain/Stop Loss
            if Posicao:
                # Condições de Saída (RSI alto OU Stop Gain OU Stop Loss)
                condicao_saida = ultimo_rsi > 70 or \
                                 (Cotacao / SIMU_PRECO_COMPRA) >= (1 + params['stop_gain']/100) or \
                                 (Cotacao / SIMU_PRECO_COMPRA) <= (1 - params['stop_loss']/100)
                
                if condicao_saida:
                    
                    valor_investido = SIMU_QNT_MOEDA * SIMU_PRECO_COMPRA
                    valor_venda = SIMU_QNT_MOEDA * Cotacao
                    LUCRO_ABS = valor_venda - valor_investido # Calcula lucro/prejuízo real

                    if LUCRO_ABS >= 0:
                        resultado = "GANHO"
                        GANHO_COUNT += 1
                    else:
                        resultado = "PREJUÍZO"
                        PERDA_COUNT += 1

                    SIMU_SALDO += valor_venda
                    
                    # Variáveis para o log
                    qnt_vendida_log = SIMU_QNT_MOEDA
                    
                    # Reset das variáveis de posição
                    Posicao = False
                    SIMU_QNT_MOEDA = 0.0
                    SIMU_PRECO_COMPRA = 0.0
                    
                    # CHAMA NOVO LOG DE VENDA
                    log_venda(
                        params['symbol'],
                        Cotacao, # Preço de venda
                        LUCRO_ABS,
                        SIMU_SALDO, # Saldo final
                        qnt_vendida_log,
                        resultado,
                        GANHO_COUNT,
                        PERDA_COUNT
                    )

    except Exception as e:
        enviar_log_geral(f"ERRO durante a operação simulada: {e}")

# =========================
# Loop do bot
# =========================
def bot_loop():
    """Loop principal que executa a operação de simulação em um intervalo definido."""
    global rodando
    enviar_log_geral("Loop do Bot de Simulação iniciado.")
    while rodando:
        operacao_simulada()
        time.sleep(5) # Ajustado para 5 segundos para reduzir a carga de requisições

# =========================
# Funções para iniciar/parar
# =========================
def iniciar_bot(novos_params=None):
    """Inicia o bot em um thread separado."""
    global rodando, params
    if rodando:
        enviar_log_geral("Bot já está rodando.")
        return False
        
    if novos_params:
        params.update(novos_params)
        
    rodando = True
    # Daemon=True garante que a thread feche quando a thread principal do Flask fechar
    threading.Thread(target=bot_loop, daemon=True).start()
    enviar_log_geral("Bot iniciado e rodando em thread separada.")
    return True

def parar_bot():
    """Para o bot."""
    global rodando
    if rodando:
        rodando = False
        enviar_log_geral("Bot parado pelo usuário.")
        return True
    return False

def get_status():
    """Retorna o status atual do bot e do saldo simulado."""
    return {
        "rodando": rodando,
        "symbol": params['symbol'],
        "saldo_usd": f"{SIMU_SALDO:.2f}",
        "em_posicao": Posicao,
        "cotacao_atual": f"{Cotacao:.2f}",
        "quantidade_moeda": f"{SIMU_QNT_MOEDA:.8f}",
        "preco_compra": f"{SIMU_PRECO_COMPRA:.2f}",
        "trades_ganhos": GANHO_COUNT,
        "trades_perdidos": PERDA_COUNT,
        "estrategia_ativa": params['estrategia'],
        "params": params
    }
