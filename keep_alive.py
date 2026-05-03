from flask import Flask
from threading import Thread
import discord
import asyncio

app = Flask(__name__)

@app.route('/')
def home():
    return "Lost's Resort Discord Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()
