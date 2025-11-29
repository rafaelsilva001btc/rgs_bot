# ==============================================================================
# 0. IMPORTANDO BIBLIOTECAS PARA FUNCIONAMENTO DO BOT
# ==============================================================================
import threading
import time
from datetime import datetime
import os
import pandas as pd

# Imports de Análise e Binance
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException, BinanceRequestException
import requests
from requests.exceptions import ReadTimeout, ConnectionError
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import BollingerBands

# ==============================================================================
# 1. CONFIGURAÇÕES E CLIENTE API
# ==============================================================================

# INTERFACE COM TELEGRAM
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8083480263:AAFdlSu5_ps9rfVBPUBzOntpvM7wU2F3mqQ")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "826927449")

# Chaves API (Use variáveis de ambiente ou deixe vazio para dados públicos)
API_KEY = os.environ.get("BINANCE_API_KEY", '') 
API_SECRET = os.environ.get("BINANCE_API_SECRET", '')

client = Client(API_KEY, API_SECRET)

# ==============================================================================
# 2. DECLARAÇÃO DE VARIÁVEIS DE ESTADO (GLOBAIS)
# ==============================================================================
Cotacao = 0.0
rodando = False
Posicao = False
bot_thread = None

# VARIAVEIS DE CONFIGURAÇÃO (Serão atualizadas via Web)
SIMU_SYMBOL = "BTCUSDT"
SIMU_MODO = "SIMULADO"
SIMU_STR = "RSI + Médias"
SIMU_RSI_PERIOD = 14
SIMU_EMA_CURTA = 9
SIMU_EMA_LONGA = 21
SIMU_INTERVALO = "1m"
SIMU_LIMIT_KLINES = 150

# VARIAVEIS DE SIMULAÇÃO (Estado do Bot)
SIMU_SALDO = 100.00
SIMU_VAL_ENTRADA = 10.00
SIMU_STOP_GAIN_PERC = 2.0
SIMU_STOP_LOSS_PERC = 2.0
SIMU_STOP_GAIN = 0.0
SIMU_STOP_LOSS = 0.0

SIMU_VAL_COMPRA = 0.0
SIMU_QNT_MOEDA = 0.0
SIMU_LUCRO_VENDA = 0.0
SIMU_SALDO_POS_VENDA = 0.0
SIMU_CONT_TRADE = 0.0
SIMU_CONT_GAIN = 0.0
SIMU_CONT_LOSS = 0.0
SIMU_LUCRO_TRADE = 0.0
SIMU_COMPRA_MAN = False
SIMU_VENDA_MAN = False
SIMU_DESAB_AUTO = False

# Variáveis de Bollinger Bands
SIMU_BB_LOW_ATUADA = False
SIMU_BB_TOP_ATUADA = False


# ==============================================================================
# 3. FUNÇÕES DE LOG E UTILITÁRIOS
# ==============================================================================

# Enviar mensagem via telegram
def enviar_log(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Erro ao enviar mensagem Telegram: {e}")

def log_compra(symbol, preco, saldo_antes, Valor_entrada, total_moeda):
    msg = (
        f"🟢 *COMPRA EXECUTADA*\n"
        f"Moeda: *{symbol}*\n"
        f"Preço de Compra: *{preco:.4f}*\n"
        f"Valor de entrada: *{Valor_entrada:.2f}*\n"
        f"Saldo: *{saldo_antes:.4f}*\n"
        f"Total moeda: *{total_moeda:.8f}*\n"
        f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    enviar_log(msg)

def log_venda(symbol, preco, lucro, saldo, Qnt_trade, resultado, ganho, perda):
    msg = (
        f"🔴 *VENDA EXECUTADA*\n"
        f"Moeda: *{symbol}*\n"
        f"Preço de Venda: *{preco:.4f}*\n"
        f"Lucro/Prejuízo: *{lucro:.6f}*\n"
        f"Saldo: *{saldo:.6f}*\n"
        f"Qnt trade: *{Qnt_trade:.1f}*\n"
        f"*{resultado}*\n"
        f"Qnt Ganho: *{ganho:.1f}*\n"
        f"Qnt Perda: *{perda:.1f}*\n"
        f"Horário: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    enviar_log(msg)

# Função para obter cotação atual
def get_price(symbol):
    global Cotacao
    try:
        # Tenta obter a cotação
        ticker = client.get_symbol_ticker(symbol=symbol)
        Cotacao = float(ticker['price'])
        return Cotacao
    except (ReadTimeout, ConnectionError):
        print("⏳ Timeout ao consultar preço, tentando novamente...")
        time.sleep(1)
    except Exception as e:
        # Se as chaves API não forem válidas, a conexão pode falhar
        print(f"⚠️ Erro na API Binance ou chaves inválidas: {e}")
        time.sleep(2)
    return Cotacao

# Função de indicadores
def calcular_indicadores(df, rsi_periodo, ema_curta_periodo, ema_longa_periodo, bb_periodo=20, bb_std=2):
    # RSI
    rsi = RSIIndicator(close=df['close'], window=rsi_periodo)
    df['RSI'] = rsi.rsi()

    # EMA Curta
    ema1 = EMAIndicator(close=df['close'], window=ema_curta_periodo)
    df['EMA1'] = ema1.ema_indicator()

    # EMA Longa
    ema = EMAIndicator(close=df['close'], window=ema_longa_periodo)
    df['EMA'] = ema.ema_indicator()

    # BOLLINGER BANDS
    bb = BollingerBands(close=df['close'], window=bb_periodo, window_dev=bb_std)
    df['BB_MID'] = bb.bollinger_mavg()
    df['BB_UP'] = bb.bollinger_hband()
    df['BB_LOW'] = bb.bollinger_lband()
    
    return df


# ==============================================================================
# 4. FUNÇÃO PRINCIPAL DE OPERAÇÃO (EXECUTADA A CADA LOOP)
# ==============================================================================

def operacao_simulada():
    """ Contém a lógica de trading, verifica indicadores e executa compra/venda. """
    global SIMU_SALDO, SIMU_VAL_ENTRADA, Posicao, Cotacao
    global SIMU_QNT_MOEDA, SIMU_CONT_GAIN, SIMU_CONT_LOSS, SIMU_CONT_TRADE
    global SIMU_COMPRA_MAN, SIMU_VENDA_MAN, SIMU_LUCRO_TRADE, SIMU_DESAB_AUTO
    global SIMU_STOP_GAIN, SIMU_STOP_LOSS, SIMU_BB_LOW_ATUADA, SIMU_BB_TOP_ATUADA
    global SIMU_RSI_PERIOD, SIMU_EMA_CURTA, SIMU_EMA_LONGA, SIMU_LIMIT_KLINES
    
    # 1. Atualiza cotação em tempo real
    Cotacao = get_price(SIMU_SYMBOL)
    if Cotacao == 0.0:
        return

    # 2. Atualiza Stops
    SIMU_STOP_GAIN = (SIMU_STOP_GAIN_PERC * SIMU_VAL_ENTRADA) / 100
    SIMU_STOP_LOSS = (-SIMU_STOP_LOSS_PERC * SIMU_VAL_ENTRADA) / 100

    # 3. BAIXANDO DADOS E INDICADORES
    try:
        klines = client.get_historical_klines(
            SIMU_SYMBOL, SIMU_INTERVALO, 
            f"{(SIMU_LIMIT_KLINES + 2)} periods ago UTC"
        )
    except Exception as e:
        print(f"Erro ao obter Klines: {e}")
        return

    df = pd.DataFrame(klines, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'trades', 'taker_base', 'taker_quote', 'ignore'
    ])
    df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)
    df = df.iloc[:-1] # Remove candle em formação (opcionalmente)

    if len(df) < max(SIMU_RSI_PERIOD, SIMU_EMA_CURTA, SIMU_EMA_LONGA, 20):
        return

    df = calcular_indicadores(df, SIMU_RSI_PERIOD, SIMU_EMA_CURTA, SIMU_EMA_LONGA)

    # Pega valores mais recentes do kendo FECHADO
    rsi = df['RSI'].iloc[-1]
    ema_curta = df['EMA1'].iloc[-1] 
    ema_longa = df['EMA'].iloc[-1]
    close = df['close'].iloc[-1]
    low = df['low'].iloc[-1]

    # Pega valores anteriores para detectar CRUZAMENTO
    ema_curta_prev = df['EMA1'].iloc[-2]
    ema_longa_prev = df['EMA'].iloc[-2]

    # Pega Bollinger Bands
    bb_low = df['BB_LOW'].iloc[-1]
    bb_up  = df['BB_UP'].iloc[-1]

    # Checa condição BB Low/Top (usando o low/close do kendo anterior)
    SIMU_BB_LOW_ATUADA = (low < bb_low)
    SIMU_BB_TOP_ATUADA = (close >= bb_up)
    
    
# ==============================
#       CONDIÇÃO DE COMPRA
# ==============================
    if not Posicao:
        # Condições de Compra
        condicao_cruzamento = (ema_curta_prev < ema_longa_prev) and (ema_curta > ema_longa) and not SIMU_DESAB_AUTO
        condicao_bb_compra = SIMU_BB_LOW_ATUADA and not SIMU_DESAB_AUTO

        if SIMU_COMPRA_MAN or condicao_cruzamento or condicao_bb_compra:
            print(f"📈 SINAL DE COMPRA: {SIMU_SYMBOL}")
            
            if SIMU_SALDO < SIMU_VAL_ENTRADA:
                print("ERRO: Saldo insuficiente para a entrada.")
                SIMU_COMPRA_MAN = False
                return

            # Executa a compra
            SIMU_QNT_MOEDA = round(SIMU_VAL_ENTRADA / Cotacao, 8)
            SIMU_SALDO -= SIMU_VAL_ENTRADA
            
            log_compra(SIMU_SYMBOL, Cotacao, SIMU_SALDO, SIMU_VAL_ENTRADA, SIMU_QNT_MOEDA)
            Posicao = True
            SIMU_COMPRA_MAN = False
            SIMU_BB_LOW_ATUADA = False

    
# ==============================
#       CÁLCULO E CONDIÇÃO DE VENDA
# ==============================
    if Posicao:
        # Lucro atual baseado na cotação em tempo real (Cotacao)
        lucro_bruto = (SIMU_QNT_MOEDA * Cotacao) - SIMU_VAL_ENTRADA
        lucro_atual = lucro_bruto * 20 # Multiplicador usado no código original
        
        # Condições de Venda
        condicao_stop_gain = (lucro_atual >= SIMU_STOP_GAIN)
        condicao_stop_loss = (lucro_atual <= SIMU_STOP_LOSS)
        condicao_bb_venda = (SIMU_BB_TOP_ATUADA and lucro_atual > 0.0)

        if SIMU_VENDA_MAN or condicao_stop_gain or condicao_stop_loss or condicao_bb_venda:
            print(f"📉 SINAL DE VENDA: {SIMU_SYMBOL}")

            # Executa a venda
            SIMU_LUCRO_VENDA = (SIMU_QNT_MOEDA * Cotacao) 
            SIMU_LUCRO_TRADE = (SIMU_LUCRO_VENDA - SIMU_VAL_ENTRADA) * 20 # Multiplicador usado no código original
            SIMU_SALDO += (SIMU_VAL_ENTRADA + SIMU_LUCRO_TRADE)
            
            SIMU_CONT_TRADE += 1

            if SIMU_LUCRO_TRADE > 0:
                SIMU_CONT_GAIN += 1
                resultado_msg = "🟢 GAIN! 💰📈"
            else:
                SIMU_CONT_LOSS += 1
                resultado_msg = "🔴 LOSS! 💸📉"

            log_venda(
                SIMU_SYMBOL, 
                Cotacao, 
                SIMU_LUCRO_TRADE, 
                SIMU_SALDO, 
                SIMU_CONT_TRADE, 
                resultado_msg,
                SIMU_CONT_GAIN,
                SIMU_CONT_LOSS
            )
            
            # Reset dos estados
            SIMU_QNT_MOEDA = 0.0
            SIMU_VENDA_MAN = False
            SIMU_COMPRA_MAN = False
            SIMU_DESAB_AUTO = False
            SIMU_BB_LOW_ATUADA = False
            SIMU_BB_TOP_ATUADA = False
            Posicao = False


# ==============================================================================
# 5. FUNÇÕES EXPORTADAS (INTERFACE COM FLASK)
# ==============================================================================

def get_status():
    """ Retorna o estado atual do bot para a interface web. """
    global SIMU_SALDO, SIMU_VAL_ENTRADA, Posicao, Cotacao, rodando, SIMU_QNT_MOEDA
    
    lucro_atual = 0.0
    if Posicao and Cotacao > 0 and SIMU_QNT_MOEDA > 0:
        lucro_bruto = (SIMU_QNT_MOEDA * Cotacao) - SIMU_VAL_ENTRADA
        lucro_atual = lucro_bruto * 20 

    status = {
        "rodando": rodando,
        "conectado": (Cotacao > 0),
        "posicao_aberta": Posicao,
        "cotacao": f"{Cotacao:.4f}",
        "lucro_atual": f"{lucro_atual:.6f}",
        "saldo": f"{SIMU_SALDO:.4f}",
        "cont_gain": f"{SIMU_CONT_GAIN:.0f}",
        "cont_loss": f"{SIMU_CONT_LOSS:.0f}",
        "cont_trade": f"{SIMU_CONT_TRADE:.0f}",
        "symbol": SIMU_SYMBOL,
        "modo": SIMU_MODO,
        "estrategia": SIMU_STR,
        "val_entrada": f"{SIMU_VAL_ENTRADA:.2f}",
        "stop_gain_perc": f"{SIMU_STOP_GAIN_PERC:.1f}",
        "stop_loss_perc": f"{SIMU_STOP_LOSS_PERC:.1f}",
        "rsi_period": f"{SIMU_RSI_PERIOD}",
        "ema_curta": f"{SIMU_EMA_CURTA}",
        "ema_longa": f"{SIMU_EMA_LONGA}",
        "tempo_grafico": SIMU_INTERVALO,
        "lim_kendos": f"{SIMU_LIMIT_KLINES}",
    }
    return status

def update_config(data):
    """ Atualiza as variáveis de configuração globais com base no JSON recebido. """
    global SIMU_SALDO, SIMU_VAL_ENTRADA, SIMU_SYMBOL, SIMU_MODO, SIMU_STR
    global SIMU_STOP_GAIN_PERC, SIMU_STOP_LOSS_PERC
    global SIMU_RSI_PERIOD, SIMU_EMA_CURTA, SIMU_EMA_LONGA, SIMU_INTERVALO, SIMU_LIMIT_KLINES

    # Não faz sentido converter 'SIMU_MODO' e 'SIMU_STR' para float, mantendo as conversões corretas
    SIMU_SYMBOL = data.get('symbol', SIMU_SYMBOL)
    SIMU_MODO = data.get('mode', SIMU_MODO)
    SIMU_STR = data.get('str', SIMU_STR)
    
    SIMU_SALDO = float(data.get('saldo', SIMU_SALDO))
    SIMU_VAL_ENTRADA = float(data.get('valEntrada', SIMU_VAL_ENTRADA))
    SIMU_STOP_GAIN_PERC = float(data.get('stopGain', SIMU_STOP_GAIN_PERC))
    SIMU_STOP_LOSS_PERC = float(data.get('stopLoss', SIMU_STOP_LOSS_PERC))
    
    SIMU_RSI_PERIOD = int(data.get('rsiPeriod', SIMU_RSI_PERIOD))
    SIMU_EMA_CURTA = int(data.get('emaCurta', SIMU_EMA_CURTA))
    SIMU_EMA_LONGA = int(data.get('emaLonga', SIMU_EMA_LONGA))
    SIMU_LIMIT_KLINES = int(data.get('limKendos', SIMU_LIMIT_KLINES))
    
    SIMU_INTERVALO = data.get('tempoGrafico', SIMU_INTERVALO)
    
    return True

def simu_comprar():
    """ Ativa a flag de compra manual. """
    global SIMU_COMPRA_MAN, SIMU_VENDA_MAN, SIMU_DESAB_AUTO, Posicao
    if Posicao:
        print("Já existe uma posição aberta. Compra Manual ignorada.")
        return False
        
    SIMU_DESAB_AUTO = True
    SIMU_VENDA_MAN = False
    SIMU_COMPRA_MAN = True
    print("SINAL MANUAL: COMPRA ativada.")
    return True
    
def simu_vender():
    """ Ativa a flag de venda manual. """
    global SIMU_COMPRA_MAN, SIMU_VENDA_MAN, SIMU_DESAB_AUTO, Posicao
    if not Posicao:
        print("Nenhuma posição para vender. Venda Manual ignorada.")
        return False
        
    SIMU_COMPRA_MAN = False
    SIMU_VENDA_MAN = True
    SIMU_DESAB_AUTO = False # Reativa auto após venda manual
    print("SINAL MANUAL: VENDA ativada.")
    return True

def bot_loop():
    """ Loop principal do bot (roda em thread separada) """
    global rodando
    print(f"\nBOT INICIADO → Moeda: {SIMU_SYMBOL} | Modo: {SIMU_MODO}\n")
    
    while rodando:
        try:
            operacao_simulada()
        except Exception as e:
            print(f"ERRO CRÍTICO no loop: {e}")
            enviar_log(f"ERRO CRÍTICO no bot: {e}")
        time.sleep(2) # Simulação de loop a cada 2 segundos

    print("\nBOT PARADO\n")

def iniciar_bot():
    """ Inicia o loop do bot em uma nova thread. """
    global rodando, bot_thread, SIMU_SYMBOL, SIMU_MODO
    if not rodando:
        rodando = True
        bot_thread = threading.Thread(target=bot_loop)
        bot_thread.daemon = True
        bot_thread.start()
        enviar_log(f"Bot iniciado. Moeda: {SIMU_SYMBOL}, Modo: {SIMU_MODO}")
        return True
    return False
        
def parar_bot():
    """ Encerra o loop do bot. """
    global rodando
    if rodando:
        rodando = False
        enviar_log("Bot parado via web.")
        return True
    return False
