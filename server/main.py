import json
import logging
import os
from flask import Flask, request, jsonify
import mysql.connector as mysql
from datetime import datetime
from flask_cors import CORS
import psutil
import ssl
import requests
from requests.adapters import HTTPAdapter
from mysql.connector.pooling import MySQLConnectionPool

# Log ayarları
logging.basicConfig(filename='server.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# config.json dosyasını okuma
def load_config():
    try:
        # Render veya yerel ortamda çalışacak şekilde dosya yolunu belirleyelim
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        
        # config.json dosyasını açma
        with open(config_path, "r") as file:
            config = json.load(file)
        
        # Yapılandırma dosyasındaki gerekli anahtarların kontrol edilmesi
        required_keys = ["server_host", "server_port", "db_host", "db_port", "db_user", "db_password", "db_name"]
        for key in required_keys:
            if key not in config:
                logging.error(f"config.json dosyasında '{key}' eksik!")
                raise KeyError(f"'{key}' yapılandırma dosyasından eksik")
        
        return config
    except FileNotFoundError:
        logging.error("config.json dosyası bulunamadı!")
        raise
    except json.JSONDecodeError:
        logging.error("config.json dosyası geçersiz formatta!")
        raise
    except KeyError as e:
        logging.error(f"Yapılandırma hatası: {e}")
        raise

# Yapılandırmayı yükleyelim
config = load_config()

# MySQL Bağlantı Havuzu Ayarı
def create_db_pool():
    try:
        pool = MySQLConnectionPool(
            pool_name="mypool",  # Havuz adı
            pool_size=5,  # Havuz boyutu (maksimum bağlantı sayısı)
            host="biomrg5uorif5yzexef3-mysql.services.clever-cloud.com",  # Veritabanı hostu
            port=3306,  # Veritabanı portu
            user="us7i8fe3s5nxpeoz",  # Veritabanı kullanıcı adı
            password="QvIoI1LDJft3x04qwgbZ",  # Veritabanı şifresi
            database="biomrg5uorif5yzexef3"  # Veritabanı adı
        )
        return pool
    except mysql.Error as e:
        logging.error(f"Veritabanı bağlantı havuzu oluşturulurken hata oluştu: {str(e)}")
        raise

# Veritabanına bağlantı al
def get_db_connection():
    try:
        pool = create_db_pool()  # Havuzu oluştur
        conn = pool.get_connection()  # Havuzdan bir bağlantı al
        return conn
    except mysql.Error as e:
        logging.error(f"Veritabanı bağlantısı alırken hata oluştu: {str(e)}")
        raise

# Ethernet (MAC) adresini almak için
def get_mac_address():
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            # Windows: "Ethernet", Linux: "eth" veya "enp" ile başlayan arayüzleri al
            if interface.lower().startswith(("ethernet", "eth", "enp")):
                for addr in addrs:
                    if addr.family == psutil.AF_LINK:  # MAC adresi
                        return addr.address  # İlk bulunan Ethernet MAC adresini döndür
    except Exception as e:
        logging.error(f"Hata oluştu: {e}")
    
    return "Ethernet MAC adresi bulunamadı"

mac_address = get_mac_address()
logging.info(f"MAC Adresi: {mac_address}")

# SSLContext ayarları - SSL hatalarını engellemek için
def create_ssl_context():
    context = ssl.create_default_context()
    context.set_ciphers('ALL')  # Tüm şifreleme yöntemlerini kabul et
    return context

# Flask uygulaması
app = Flask(__name__)

# CORS'u tüm uygulamaya ekleyelim
CORS(app)  # Flask uygulamasına CORS desteğini ekler

# POST isteği ile cihaz bilgisi alacak endpoint
@app.route('/receive_device_info', methods=['POST'])
def receive_device_info():    
    data = request.get_json()  # Gelen JSON verisini al
    if not data:
        logging.warning("Boş veri alındı!")
        return jsonify({"error": "Veri alınamadı"}), 400

    # Gerekli alanları kontrol et
    required_fields = ["system_info", "memory_info", "cpu_info", "disk_info", "os_info", "installed_software", "uptime", "boot_time"]
    for field in required_fields:
        if field not in data:
            logging.warning(f"{field} eksik!")
            return jsonify({"error": f"'{field}' alanı eksik"}), 400    

    # Veritabanına bağlan
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM devices WHERE mac_address = %s", (mac_address,))
    device_exists = cursor.fetchone()
    logging.info(f"device_exists: {device_exists}")

    if device_exists is not None:
        agent_id = data['agent_id']

        # Agent ID veritabanında var mı kontrol et
        cursor.execute("SELECT id FROM agent WHERE agent_id = %s", (agent_id,))
        result = cursor.fetchone()

        if result is None:
            # Yeni bir agent ID eklemek için INSERT sorgusu
            cursor.execute("INSERT INTO agent (agent_id) VALUES (%s)", (agent_id,))
            conn.commit()
            logging.info(f"Yeni Agent ID ekledi: {agent_id}")
        else:
            # Eğer mevcutsa, mevcut agent_id'yi al
            existing_agent_id = result[0]
            logging.info(f"Mevcut Agent ID: {existing_agent_id}")

        # Diğer bilgiler, örneğin sistem bilgisi, bellek bilgisi, yazılım bilgileri vs. eklenebilir.
        system_info = data['system_info']
        cursor.execute("""SELECT id FROM system_info WHERE agent_id = %s AND `system` = %s AND node_name = %s
        AND `release` = %s AND version = %s AND machine = %s AND processor = %s""", 
        (agent_id, system_info['system'], system_info['node_name'], system_info['release'],
        system_info['version'], system_info['machine'], system_info['processor']))
        existing_system_info = cursor.fetchone()

        if existing_system_info is None:
            query_system_info = """
            INSERT INTO system_info (agent_id, `system`, node_name, `release`, version, machine, processor)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            system_values = (agent_id, system_info['system'], system_info['node_name'], system_info['release'], 
            system_info['version'], system_info['machine'], system_info['processor'])
            cursor.execute(query_system_info, system_values)
            conn.commit()
            logging.info("Yeni sistem bilgisi eklendi.")
        else:
            logging.info("Sistem bilgisi zaten mevcut.")

        # Veritabanı bağlantısını kapat
        cursor.close()
        conn.close()

        return jsonify({"message": "Veri başarıyla alındı"}), 200

# Sunucuya HTTPS üzerinden veri gönderirken SSL hatalarından kaçınmak için
@app.route('/send_device_info', methods=['POST'])
def send_device_info():
    url = "https://network-monitoring-4jg5.onrender.com/receive_device_info"
    
    # SSLContext oluşturuluyor
    context = create_ssl_context()

    data = {
        # Göndermek istediğiniz JSON verisini buraya ekleyin
    }

    # requests için SSLContext ile bağlantı yap
    try:
        with requests.Session() as session:
            adapter = HTTPAdapter(ssl_context=context)
            session.mount('https://', adapter)

            response = session.post(url, json=data)
            logging.info(f"Sunucu yanıtı: {response.status_code}, {response.text}")
            return jsonify({"message": "Veri gönderildi", "status": response.status_code, "response": response.text}), 200
    except requests.exceptions.RequestException as e:
        logging.error(f"Sunucuya veri gönderirken hata oluştu: {e}")
        return jsonify({"error": "Veri gönderilemedi"}), 500

if __name__ == "__main__":
    app.run(host=config['server_host'], port=config['server_port'], debug=False)

