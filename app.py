
# ПРЕЗИНТАЦИЯ
import re

from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session, flash,send_file
from flask_caching import Cache
import psycopg2
from psycopg2 import OperationalError
import qrcode
import io
import base64
from flask_socketio import SocketIO, emit, join_room
from babel.dates import format_date
from datetime import datetime
import locale
from datetime import datetime, timedelta
from PIL import Image
import os
import dotenv
dotenv.load_dotenv()

locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8')


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
socketio = SocketIO(app, cors_allowed_origins="*")
cache = Cache(app, config={"CACHE_TYPE": "simple"})


# Подключение к базе данных для авторизации (для проверки данных входа)
def get_auth_db_connection():
    try:
        conn = psycopg2.connect(
            host="localhost",  # Адрес PostgreSQL сервера
            dbname="authdb",  # Имя базы данных для авторизации
            user="samandarlev",  # Имя пользователя
            password="1956"  # Пароль пользователя
        )
        return conn
    except OperationalError as e:
        print(f"Ошибка подключения к базе данных авторизации: {e}")
        return None



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone_number = request.form['phone_number']
        password = request.form['password']

        # Проверка на менеджера
        conn = get_auth_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM managers WHERE phone_number = %s AND password = %s", (phone_number, password))
        manager = cursor.fetchone()

        if manager:
            session['manager_id'] = manager[0]  # Сохраняем ID менеджера в сессии
            return redirect(url_for('select_number'))  # Перенаправляем менеджера на страницу выбора номера

        # Проверка на организацию
        cursor.execute("SELECT id FROM organizations WHERE phone_number = %s AND password = %s", (phone_number, password))
        organization = cursor.fetchone()
        conn.close()

        if organization:
            session['organization_id'] = organization[0]  # Сохраняем ID организации в сессии
            return redirect(url_for('admin_qr'))  # Перенаправляем организацию на страницу QR

        # Если ни одна из проверок не прошла
        return "Неверный номер или пароль", 401
    
    return render_template('login.html')


@app.route('/')
def admin_qr():
    if 'organization_id' not in session:
        return redirect(url_for('login'))  # Перенаправление на вход
    
    organization_id = session['organization_id']
    qr_data = f"https://9c35-37-151-83-167.ngrok-free.app/client?org_id={organization_id}"

    # Создаём QR-код с высокой коррекцией ошибок
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # H = 30% коррекции (чтобы лого не мешало сканированию)
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Генерируем QR-код как изображение
    qr_img = qr.make_image(fill="black", back_color="white").convert("RGBA")

    # Загружаем логотип

    logo_path = "static/images/icon.png"  # Путь к логотипу



    logo = Image.open(logo_path)

    # Изменяем размер логотипа (примерно 20% от размера QR-кода)
    qr_width, qr_height = qr_img.size
    logo_size = qr_width // 4  # 1/4 от QR-кода

    logo = logo.resize((logo_size, logo_size))


    # Вычисляем позицию логотипа (центр QR-кода)
    logo_position = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)

    # Накладываем логотип на QR-код

    qr_img.paste(logo, logo_position)


    # Конвертируем в base64
    img_io = io.BytesIO()
    qr_img.save(img_io, format='PNG')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.getvalue()).decode('utf-8')

    return render_template('tablet.html', img_base64=img_base64)

def normalize_phone_number(phone_number):
    # Убираем все нецифровые символы из номера
    digits = re.sub(r'\D', '', phone_number)
    # Форматируем номер в нужный вид
    return f"+7 ({digits[1:4]}) {digits[4:7]} {digits[7:9]} {digits[9:11]}"

@app.route('/client', methods=['GET', 'POST'])
def client():
    org_id = request.args.get('org_id')
    visit_id = None
    phone_number = None
    
    # Получаем номер из формы или параметров URL
    if request.method == 'POST':
        phone_number = request.form['phone_number']  # Получаем номер из формы
    elif request.method == 'GET':
        phone_number = request.args.get('number')  # Получаем номер из параметров URL

    if phone_number:
        # Нормализуем номер телефона, чтобы сравнение было корректным
        phone_number = normalize_phone_number(phone_number)

        conn = get_auth_db_connection()
        cursor = conn.cursor()

        # Проверяем, есть ли такой номер в базе данных
        cursor.execute("SELECT id, name, surname, end_subscription FROM users WHERE phone = %s", (phone_number,))
        users = cursor.fetchone()

        # Проверяем, существует ли организация
        cursor.execute("SELECT id, name FROM organizations WHERE id = %s", (org_id,))
        organization = cursor.fetchone()

        if users and organization:
            # Получаем дату окончания абонемента
            end_subscription = users[3]

            # Проверяем, не истек ли абонемент
            if end_subscription and end_subscription.date() < datetime.now().date():
                # Если абонемент истек
                return "<h1>Ошибка: ваш абонемент завершен!</h1>", 400
            
            # Создаем запись о посещении, если абонемент активен
            cursor.execute(
                "INSERT INTO visits (user_id, organization_id, client_first_name, client_last_name, organization_name, status) "
                "VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING id",
                (users[0], org_id, users[1], users[2], organization[1])
            )

            visit_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()

            socketio.emit('client_verified', {'organization_id': org_id}, room=org_id)

            # Если номер передан через URL, сразу перенаправляем на страницу good_client с visit_id
            if request.method == 'GET':
                return redirect(url_for('good_client', visit_id=visit_id))
            elif request.method == 'POST':
                return redirect(url_for('good_client', visit_id=visit_id))

        else:
            return "<h1>Ошибка: клиент или организация не найдены!</h1>", 404

    return render_template("client.html", org_id=org_id)



@app.route('/good_client/<int:visit_id>', methods=['GET'])
def good_client(visit_id):
    conn = get_auth_db_connection()
    cursor = conn.cursor()
    
    # Получаем данные о посещении, организации и времени
    cursor.execute("""
        SELECT v.client_first_name, v.client_last_name, o.name, v.visit_time
        FROM visits v
        JOIN organizations o ON v.organization_id = o.id
        WHERE v.id = %s
    """, (visit_id,))
    
    visit_data = cursor.fetchone()
    conn.close()

    if visit_data:
        client_first_name, client_last_name, organization_name, visit_time = visit_data
        # Преобразуем время в нужный формат
        visit_time = visit_time.strftime('%Y-%m-%d %H:%M:%S')
        return render_template('good_client.html', visit_id=visit_id, 
                               client_first_name=client_first_name, 
                               client_last_name=client_last_name, 
                               organization_name=organization_name,
                               visit_time=visit_time)
    else:
        return "<h1>Ошибка: не найдено посещение!</h1>", 404



@app.route('/good/<int:visit_id>', methods=['GET'])
def good(visit_id):
    # Обрабатываем visit_id
    return render_template('good.html', visit_id=visit_id)





@app.route('/logout')
def logout():
    session.pop('organization_id', None)  # Удаляем информацию о сессии
    return redirect(url_for('login'))  # Перенаправляем на страницу логина

@socketio.on('join')
def handle_join(data):
    organization_id = data.get("organization_id")
    join_room(organization_id)
    print(f"✅ Админская страница подключилась к комнате: {organization_id}")



def get_visits_by_organization(org_id, date_filter="all"):
    conn = get_auth_db_connection()
    cursor = conn.cursor()

    sql = """
        SELECT client_first_name, client_last_name, visit_time
        FROM visits
        WHERE organization_id = %s
    """
    params = [org_id]

    now = datetime.now()

    if date_filter == "today":
        start = now.replace(hour=0, minute=0, second=0)
        end = now.replace(hour=23, minute=59, second=59)
        sql += " AND visit_time BETWEEN %s AND %s"
        params.extend([start, end])
    
    elif date_filter == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        sql += " AND visit_time BETWEEN %s AND %s"
        params.extend([start, end])

    elif date_filter == "week":
        start = now - timedelta(days=7)
        sql += " AND visit_time >= %s"
        params.append(start)

    sql += " ORDER BY visit_time DESC"

    cursor.execute(sql, params)
    visits = cursor.fetchall()

    cursor.close()
    conn.close()

    return visits



@app.route('/history', methods=['GET'])
def history():
    if 'organization_id' not in session:
        return redirect(url_for('login'))

    org_id = session['organization_id']
    date_filter = request.args.get('date_filter', 'all')  # Фильтр по времени

    # Определяем, какую дату отображать
    if date_filter == "today":
        display_date = datetime.now().strftime('%d %B %Y')  # Сегодняшняя дата
    elif date_filter == "yesterday":
        display_date = (datetime.now() - timedelta(days=1)).strftime('%d %B %Y')  # Вчерашняя дата
    else:
        display_date = None  # Не отображаем дату для остальных фильтров

    visits = get_visits_by_organization(org_id, date_filter)

    return render_template('history.html', 
                           visits=visits, 
                           org_id=org_id, 
                           date_filter=date_filter, 
                           display_date=display_date)



@app.route('/select_number', methods=['GET'])
def select_number():
    if 'manager_id' not in session:
        return redirect(url_for('login'))  # Если нет менеджера в сессии, перенаправляем на вход

    # Получаем имя менеджера
    manager_id = session['manager_id']
    conn = get_auth_db_connection()
    cursor = conn.cursor()

    # Получаем имя и фамилию менеджера
    cursor.execute("""
        SELECT manager_name, manager_last_name
        FROM managers
        WHERE id = %s
    """, (manager_id,))
    manager = cursor.fetchone()

    if manager:
        manager_name = f"{manager[0]}"  # Имя и фамилия менеджера
    else:
        manager_name = "Неизвестный менеджер"  # Если менеджера не нашли, выводим сообщение

    # Получаем клиентов
    phone_query = request.args.get('phone', '')
    if phone_query:
        cursor.execute("""
            SELECT name, surname, phone 
            FROM users
            WHERE phone LIKE %s
        """, (f"%{phone_query}%",))
    else:
        cursor.execute("""
            SELECT name, surname, phone 
            FROM users
        """)
    
    clients = cursor.fetchall()
    conn.close()

    return render_template('select_number.html', 
                           clients=clients, 
                           phone_query=phone_query,
                           manager_name=manager_name)  # Передаем имя менеджера в шаблон

@app.route('/select_organization')
def select_organization():
    if 'manager_id' not in session:
        return redirect(url_for('login'))

    number = request.args.get('number')
    search_query = request.args.get('search', '')

    if not number:
        return redirect(url_for('select_number'))

    conn = get_auth_db_connection()
    cursor = conn.cursor()

    # Получаем имя клиента по номеру
    cursor.execute("SELECT name, surname FROM users WHERE phone = %s", (number,))
    client = cursor.fetchone()

    # Поиск организаций по названию
    if search_query:
        cursor.execute("SELECT id, name FROM organizations WHERE name LIKE %s", (f"%{search_query}%",))
    else:
        cursor.execute("SELECT id, name FROM organizations")

    organizations = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'select_organization.html',
        number=number,
        organizations=organizations,
        client_name=f"{client[0]} {client[1]}" if client else "Неизвестный клиент",
        search_query=search_query
    )



@app.route('/generate_link')
def generate_link():
    number = request.args.get('number')
    org_id = request.args.get('org_id')

    if not number or not org_id:
        return redirect(url_for('select_number'))

    client_url = f"{request.host_url}client?number={number}&org_id={org_id}"

    return render_template('generate_link.html', client_url=client_url)






if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=5002)



















