"""
🚗 ALPR FINAL DASHBOARD v3 - Claude Vision API
- Claude Vision API + Flask + Arduino
- Реальное управление шлагбаумом, LED и дисплеями
- Кнопки: 📘 БАЗА, 🔄 ОБНОВИТЬ БАЗУ, 📜 ИСТОРИЯ
"""

import cv2
import os
import time
import serial
import platform
import threading
import base64
import anthropic
from datetime import datetime
from flask import Flask, Response, render_template_string, redirect, url_for

# === Настройки API ===
ANTHROPIC_API_KEY = "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"
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# === Настройки путей ===
BASE_DIR = r"C:\esp32_project"
DB_PATH = os.path.join(BASE_DIR, "database.txt")
LOG_PATH = os.path.join(BASE_DIR, "logs.csv")
CAPTURE_DIR = os.path.join(BASE_DIR, "captures_v3")
os.makedirs(CAPTURE_DIR, exist_ok=True)

# === Настройки камеры ===
CAMERA_INDEX = 1
PROCESS_EVERY_N_FRAMES = 30  # Реже обрабатываем (API дороже)
MIN_PLATE_LEN = 4

# === Arduino подключение ===
try:
    arduino = serial.Serial("COM3", 115200, timeout=1)
    print("✅ Arduino подключена к COM3")
except Exception as e:
    arduino = None
    print(f"⚠️ Arduino не найдена: {e}")

def send_to_arduino(cmd):
    if arduino and arduino.is_open:
        arduino.write((cmd + "\n").encode())
        print(f"➡️ Arduino: {cmd}")

# === Звук (только для Windows) ===
if platform.system() == "Windows":
    import winsound
    def beep_success(): winsound.Beep(1200, 150)
    def beep_detect(): winsound.Beep(800, 80)
else:
    def beep_success(): print("🔊 OK")
    def beep_detect(): print("🔊 DETECT")

# === Работа с базой ===
def load_db():
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            f.write("A123BC77\nE777XX99\nM999OO77\n701АІҮ02\n")
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return [line.strip().upper().replace(" ", "") for line in f if line.strip()]

ALLOWED = load_db()

# === Функции нормализации ===
def normalize_plate(text):
    text = text.upper().replace(" ", "")
    # Кириллица → Латиница
    translit = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")
    return text.translate(translit)

# === Claude Vision API для распознавания номера ===
def recognize_plate_with_claude(frame):
    """
    Отправляет кадр в Claude API и получает номер автомобиля
    """
    try:
        # Сохраняем временный файл
        temp_path = os.path.join(CAPTURE_DIR, f"temp_{int(time.time())}.jpg")
        cv2.imwrite(temp_path, frame)
        
        # Конвертируем в base64
        with open(temp_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        
        # Удаляем временный файл
        os.remove(temp_path)
        
        # Запрос к Claude
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Найди номер автомобиля на этом фото. Верни ТОЛЬКО номер автомобиля без лишнего текста, пробелов и объяснений. Если номера нет, верни 'NONE'."
                    }
                ],
            }]
        )
        
        plate_text = message.content[0].text.strip()
        
        # Если Claude что-то распознал
        if plate_text and plate_text != "NONE" and len(plate_text) >= MIN_PLATE_LEN:
            print(f"🤖 Claude распознал: {plate_text}")
            return normalize_plate(plate_text)
        
        return None
        
    except Exception as e:
        print(f"❌ Ошибка Claude API: {e}")
        return None

# === Камера-поток ===
frame_lock = threading.Lock()
latest_frame = None
latest_result = None
stop_flag = False

def capture_loop():
    global latest_frame, latest_result
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("🎥 Камера запущена")

    frame_count = 0
    while not stop_flag:
        ret, frame = cap.read()
        if not ret:
            continue

        frame_count += 1
        
        # Обрабатываем реже (API платный!)
        if frame_count % PROCESS_EVERY_N_FRAMES == 0:
            print("📸 Обрабатываем кадр...")
            
            # Распознаем номер через Claude
            plate_text = recognize_plate_with_claude(frame)
            
            if plate_text:
                # Проверяем в базе
                status = "✅ Разрешён" if plate_text in ALLOWED else "❌ Запрещён"
                color = (0, 255, 0) if "✅" in status else (0, 0, 255)
                
                # Рисуем результат на кадре
                cv2.putText(frame, f"{plate_text} {status}", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
                
                # Логируем
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                with open(LOG_PATH, "a", encoding="utf-8") as log:
                    log.write(f"{ts},{plate_text},{status}\n")
                
                # Сохраняем результат
                latest_result = {"plate": plate_text, "status": status}
                
                # Сохраняем фото
                save_path = os.path.join(CAPTURE_DIR, f"{ts}_{plate_text}.jpg")
                cv2.imwrite(save_path, frame)
                
                # === Управление Arduino ===
                if plate_text in ALLOWED:
                    send_to_arduino(f"DISPLAY:{plate_text}")
                    send_to_arduino("TRAFFIC:GREEN")
                    send_to_arduino("OPEN")
                    beep_success()
                else:
                    send_to_arduino(f"DISPLAY:{plate_text}")
                    send_to_arduino("TRAFFIC:RED")
                    beep_detect()

        # Обновляем кадр для стрима
        if frame_lock.acquire(timeout=0.01):
            latest_frame = frame.copy()
            frame_lock.release()
        
        time.sleep(0.03)
    
    cap.release()

# === Flask сервер ===
app = Flask(__name__)

@app.route("/")
def index():
    plate = latest_result['plate'] if latest_result else "-"
    status = latest_result['status'] if latest_result else "-"
    return render_template_string(f"""
    <html>
    <head>
        <title>ALPR Claude Vision</title>
        <meta http-equiv="refresh" content="2">
    </head>
    <body style="background:#111;color:white;text-align:center;font-family:Arial">
      <h2>🚗 ALPR + Claude Vision API</h2>
      <img src="/video_feed" width="640" height="480"><br><br>
      <h3>Последний результат: <span style="font-size:28px">{plate}</span> {status}</h3>

      <form action="/show_db" method="get">
        <button style="padding:10px 25px;margin:5px;cursor:pointer;">📘 БАЗА</button>
      </form>
      <form action="/reload_db" method="post">
        <button style="padding:10px 25px;margin:5px;cursor:pointer;">🔄 ОБНОВИТЬ БАЗУ</button>
      </form>
      <form action="/history" method="get">
        <button style="padding:10px 25px;margin:5px;cursor:pointer;">📜 ИСТОРИЯ</button>
      </form>
    </body></html>
    """)

@app.route("/video_feed")
def video_feed():
    def gen():
        while True:
            frame_copy = None
            if frame_lock.acquire(timeout=0.01):
                if latest_frame is not None:
                    frame_copy = latest_frame.copy()
                frame_lock.release()
            if frame_copy is not None:
                _, buf = cv2.imencode(".jpg", frame_copy)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
            else:
                time.sleep(0.05)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/show_db")
def show_db():
    db_list = load_db()
    db_html = "<br>".join(db_list)
    return f"<html><body style='background:#111;color:white;text-align:center'><h3>📘 Текущая база:</h3><p style='font-size:20px'>{db_html}</p><br><a href='/' style='color:lime'>← Назад</a></body></html>"

@app.route("/reload_db", methods=["POST"])
def reload_db():
    global ALLOWED
    ALLOWED = load_db()
    print("🔄 База обновлена:", ALLOWED)
    beep_success()
    return "<html><body style='background:#111;color:lime;text-align:center'><h3>База успешно обновлена!</h3><a href='/' style='color:lime'>← Назад</a></body></html>"

@app.route("/history")
def history():
    if not os.path.exists(LOG_PATH):
        return "<html><body style='background:#111;color:white;text-align:center'><h3>История пуста</h3><a href='/' style='color:lime'>← Назад</a></body></html>"
    rows = open(LOG_PATH, encoding="utf-8").read().splitlines()
    table = "<table border=1 cellpadding=5 style='margin:auto;color:white;border-color:#555'><tr style='background:#333'><th>Время</th><th>Номер</th><th>Статус</th></tr>"
    for line in reversed(rows[-50:]):
        parts = line.split(",", 2)
        if len(parts) == 3:
            ts, plate, status = parts
            row_color = "#040" if "✅" in status else "#400"
            table += f"<tr style='background:{row_color}'><td>{ts}</td><td>{plate}</td><td>{status}</td></tr>"
    table += "</table><br><a href='/' style='color:lime'>← Назад</a>"
    return f"<html><body style='background:#111;color:white;text-align:center'><h2>📜 История распознаваний</h2>{table}</body></html>"

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 ALPR + Claude Vision API v3")
    print("="*50)
    print(f"📁 База данных: {DB_PATH}")
    print(f"📊 Логи: {LOG_PATH}")
    print(f"📸 Снимки: {CAPTURE_DIR}")
    print(f"🌐 Web: http://127.0.0.1:5000")
    print("="*50 + "\n")
    
    threading.Thread(target=capture_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
