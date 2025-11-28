from flask import Flask, render_template, jsonify, request
import threading
import bot_logic

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify(bot_logic.get_status())

@app.route('/start', methods=['POST'])
def start():
    data = request.json
    threading.Thread(target=bot_logic.iniciar_bot, args=(data,), daemon=True).start()
    return jsonify({"message":"Bot iniciado"})

@app.route('/stop', methods=['POST'])
def stop():
    bot_logic.parar_bot()
    return jsonify({"message":"Bot parado"})

@app.route('/buy', methods=['POST'])
def buy():
    bot_logic.operacao_simulada()
    return jsonify({"message":"Compra simulada executada"})

@app.route('/sell', methods=['POST'])
def sell():
    bot_logic.operacao_simulada()
    return jsonify({"message":"Venda simulada executada"})

if __name__ == '__main__':
    app.run(debug=True)
