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
logging.basicConfig(filename='server.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# config.json dosyasını okuma
def load_config():
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, "r") as file:
            config = json.load(file)
        
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
            if interface.lower().startswith(("ethernet", "eth", "enp")):
                for addr in addrs:
                    if addr.family == psutil.AF_LINK:
                        return addr.address
    except Exception as e:
        logging.error(f"Hata oluştu: {e}")
    
    return "Ethernet MAC adresi bulunamadı"

mac_address = get_mac_address()
logging.info(f"MAC Adresi: {mac_address}")

# SSLContext ayarları - SSL hatalarını engellemek için
def create_ssl_context():
    context = ssl.create_default_context()
    context.set_ciphers('ALL')
    return context

# Flask uygulaması
app = Flask(__name__)

# CORS'u tüm uygulamaya ekleyelim
CORS(app)

# POST isteği ile cihaz bilgisi alacak endpoint
@app.route('/receive_device_info', methods=['POST'])
def receive_device_info():
    try:
        data = request.get_json()  # Gelen JSON verisini al
        print(data)
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
        print("Conn:" + conn)
        cursor = conn.cursor()
        print("Cursor:" + cursor)

        # MAC adresi ile cihazın olup olmadığını kontrol et
        cursor.execute("SELECT * FROM devices WHERE mac_address = %s", (mac_address,))
        device_exists = cursor.fetchone()
        logging.info(f"device_exists: {device_exists}")

        if device_exists is not None:
            agent_id = data['agent_id']

            # Agent ID veritabanında var mı kontrol et
            cursor.execute("SELECT id FROM agent WHERE agent_id = %s", (agent_id,))
            result = cursor.fetchone()
            print("Result:" + result)

            if result is None:
                # Yeni bir agent ID eklemek için INSERT sorgusu
                cursor.execute("INSERT INTO agent (agent_id) VALUES (%s)", (agent_id,))
                conn.commit()
                logging.info(f"Yeni Agent ID ekledi: {agent_id}")
            else:
                # Eğer mevcutsa, mevcut agent_id'yi al
                existing_agent_id = result[0]
                logging.info(f"Mevcut Agent ID: {existing_agent_id}")

            # Sistem bilgilerini veritabanına ekleyelim
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

            # Ek bilgiler eklemek ve commit yapmak için diğer sorgular benzer şekilde yazılabilir.
            # Diğer bilgiler (memory_info, cpu_info vb.) eklemek için benzer sorguları ekleyin.

        else:
            logging.warning(f"MAC adresi {mac_address} ile cihaz bulunamadı.")

        # Veritabanı bağlantısını kapat
        cursor.close()
        conn.close()

        return jsonify({"message": "Veri başarıyla alındı"}), 200

    except mysql.Error as e:
        logging.error(f"Veritabanı işlemi hatası: {e}")
        return jsonify({"error": "Veritabanı işlemi hatası"}), 500

    except Exception as e:
        logging.error(f"Bilinmeyen bir hata oluştu: {e}")
        return jsonify({"error": "Bilinmeyen bir hata oluştu"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
