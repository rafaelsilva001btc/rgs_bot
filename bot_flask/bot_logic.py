import threading
import time
import pandas as pd
from datetime import datetime
from binance.client import Client
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

# =========================
# Configurações
# =========================
API_KEY = ''
API_SECRET = ''
client = Client(API_KEY, API_SECRET)

# =========================
# Variáveis globais
# =========================
rodando = False
Posicao = False
SIMU_SALDO = 100.0
SIMU_QNT_MOEDA = 0.0
SIMU_LUCRO_VENDA = 0.0
Cotacao = 0.0

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
# Funções auxiliares
# =========================
def enviar_log(msg):
    # Aqui poderia integrar Telegram
    print(f"[LOG] {msg}")

def get_price(symbol="BTCUSDT"):
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except:
        return 0.0

def calcular_indicadores(df, rsi_periodo, sma_periodo, ema_periodo):
    rsi = RSIIndicator(close=df['close'], window=rsi_periodo)
    df['RSI'] = rsi.rsi()
    ema1 = EMAIndicator(close=df['close'], window=sma_periodo)
    df['EMA1'] = ema1.ema_indicator()
    ema = EMAIndicator(close=df['close'], window=ema_periodo)
    df['EMA'] = ema.ema_indicator()
    return df

# =========================
# Função principal de simulação
# =========================
def operacao_simulada():
    global SIMU_SALDO, Posicao, SIMU_QNT_MOEDA, SIMU_LUCRO_VENDA, Cotacao

    klines = client.get_klines(symbol=params['symbol'], interval=params['tempo_grafico'], limit=params['limite_kendos'])
    df = pd.DataFrame(klines, columns=[
        'time','open','high','low','close','volume','close_time','qav','trades','taker_base','taker_quote','ignore'
    ])
    df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
    
    if params['estrategia'] == "RSI + Médias" and rodando:
        df = calcular_indicadores(df, params['prsi'], params['ind_SMA'], params['ind_EMA'])
        ultimo_rsi = df['RSI'].iloc[-1]
        ultima_sma = df['EMA1'].iloc[-1]
        ultima_ema = df['EMA'].iloc[-1]
        Cotacao = df['close'].iloc[-1]

        # Compra simulada
        if ultimo_rsi < 50 and ultima_ema > ultima_sma and not Posicao:
            valor_entrada = SIMU_SALDO * params['val_entrada'] / 100
            SIMU_QNT_MOEDA = round(valor_entrada / Cotacao, 8)
            SIMU_SALDO -= valor_entrada
            Posicao = True
            enviar_log(f"Compra simulada: {SIMU_QNT_MOEDA} BTC a {Cotacao}")

        # Venda simulada com Stop Gain/Stop Loss
        stopgain = SIMU_QNT_MOEDA * Cotacao * (1 + params['stop_gain']/100)
        stoploss = SIMU_QNT_MOEDA * Cotacao * (1 - params['stop_loss']/100)
        if Posicao:
            if Cotacao >= stopgain or Cotacao <= stoploss:
                SIMU_LUCRO_VENDA = SIMU_QNT_MOEDA * Cotacao
                SIMU_SALDO += SIMU_LUCRO_VENDA
                Posicao = False
                enviar_log(f"Venda simulada: lucro {SIMU_LUCRO_VENDA}")

# =========================
# Loop do bot
# =========================
def bot_loop():
    global rodando
    while rodando:
        operacao_simulada()
        time.sleep(1)

# =========================
# Funções para iniciar/parar
# =========================
def iniciar_bot(novos_params=None):
    global rodando, params
    if novos_params:
        params.update(novos_params)
    rodando = True
    threading.Thread(target=bot_loop, daemon=True).start()
    enviar_log("Bot iniciado")

def parar_bot():
    global rodando
    rodando = False
    enviar_log("Bot parado")

def get_status():
    return {
        "rodando": rodando,
        "saldo": SIMU_SALDO,
        "posicao": Posicao,
        "cotacao": Cotacao,
        "quantidade_moeda": SIMU_QNT_MOEDA,
        "lucro_venda": SIMU_LUCRO_VENDA
    }
