import json
import logging
import os
from flask import Flask, request, jsonify
import mysql.connector as mysql
from datetime import datetime
from flask_cors import CORS
import psutil

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

# MySQL veritabanına bağlantı
def connect_db():
    try:
        conn = mysql.connect(
            host=config["db_host"],
            port=config["db_port"],
            user=config["db_user"],
            password=config["db_password"],
            database=config["db_name"]
        )
        return conn
    except mysql.Error as e:
        logging.error(f"Veritabanı bağlantı hatası: {str(e)}")
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
        print(f"Hata oluştu: {e}")
    
    return "Ethernet MAC adresi bulunamadı"

mac_address = get_mac_address()
print(mac_address)

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
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM devices WHERE mac_address = %s", (mac_address,))
    device_exists = cursor.fetchone()
    print("device_exists: ", device_exists)

    if device_exists is not None:
        agent_id = data['agent_id']

        # Agent ID veritabanında var mı kontrol et
        cursor.execute("SELECT id FROM agent WHERE agent_id = %s", (agent_id,))
        result = cursor.fetchone()

        if result is None:
            # Yeni bir agent ID eklemek için INSERT sorgusu
            cursor.execute("INSERT INTO agent (agent_id) VALUES (%s)", (agent_id,))
            conn.commit()
            print(f"Yeni Agent ID ekledi: {agent_id}")
        else:
            # Eğer mevcutsa, mevcut agent_id'yi al
            existing_agent_id = result[0]
            print(f"Mevcut Agent ID: {existing_agent_id}")

        # Diğer bilgiler, örneğin sistem bilgisi, bellek bilgisi, yazılım bilgileri vs. eklenebilir.
        system_info = data['system_info']
        cursor.execute("""
        SELECT id FROM system_info WHERE agent_id = %s AND `system` = %s AND node_name = %s
        AND `release` = %s AND version = %s AND machine = %s AND processor = %s
        """, (agent_id, system_info['system'], system_info['node_name'], system_info['release'],
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
            print("Yeni sistem bilgisi eklendi.")
        else:
            print("Sistem bilgisi zaten mevcut.")

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
        conn = connect_db()
        cursor = conn.cursor()

        # Veriyi veritabanına ekleme
        query_check = "SELECT COUNT(*) FROM software_info WHERE name = %s AND version = %s"
        query_insert = "INSERT INTO software_info (id, name, version) VALUES (%s, %s, %s)"

        # Yazılım bilgilerini ekle
        for i in range(1, len(data['installed_software'])):
            software_name = data['installed_software'][i][0][:45]
            software_version = data['installed_software'][i][1][:45].replace(" ", "")
        
            # Veritabanında aynı yazılımın ismi ve sürümü olup olmadığını kontrol et
            cursor.execute(query_check, (software_name, software_version))
            result = cursor.fetchone()
        
            if result[0] == 0:  # Eğer sonuç 0 ise, veri yok demektir
                values = (i, software_name, software_version)
                cursor.execute(query_insert, values)
                conn.commit()

        # Bellek bilgileri kontrol edilip ekleniyor
        memory_info = data['memory_info']
        cursor.execute("""
        SELECT id FROM memory_info WHERE agent_id = %s AND total_memory = %s AND available_memory = %s
        AND used_memory = %s AND memory_percent = %s
        """, (agent_id, memory_info['total_memory'], memory_info['available_memory'], 
        memory_info['used_memory'], memory_info['memory_percent']))
        existing_memory_info = cursor.fetchone()

        if existing_memory_info is None:
            query_memory_info = """
            INSERT INTO memory_info (agent_id, total_memory, available_memory, used_memory, memory_percent)
            VALUES (%s, %s, %s, %s, %s)
            """
            memory_values = (agent_id, memory_info['total_memory'], memory_info['available_memory'], 
            memory_info['used_memory'], memory_info['memory_percent'])
            cursor.execute(query_memory_info, memory_values)
            conn.commit()
            print("Yeni bellek bilgisi eklendi.")
        else:
            print("Bellek bilgisi zaten mevcut.")

        # CPU bilgileri kontrol edilip ekleniyor
        cpu_info = data['cpu_info']
        cursor.execute("""
        SELECT id FROM cpu_info WHERE agent_id = %s AND cpu_percent = %s
        """, (agent_id, cpu_info['cpu_percent']))
        existing_cpu_info = cursor.fetchone()

        if existing_cpu_info is None:
            query_cpu_info = """
            INSERT INTO cpu_info (agent_id, cpu_percent)
            VALUES (%s, %s)
            """
            cpu_values = (agent_id, cpu_info['cpu_percent'])
            cursor.execute(query_cpu_info, cpu_values)
            conn.commit()
            print("Yeni CPU bilgisi eklendi.")
        else:
            print("CPU bilgisi zaten mevcut.")

        # Disk bilgileri kontrol edilip ekleniyor
        disk_info = data['disk_info']
        cursor.execute("""
        SELECT id FROM disk_info WHERE agent_id = %s AND total_disk = %s AND used_disk = %s
        AND free_disk = %s AND disk_percent = %s
        """, (agent_id, disk_info['total_disk'], disk_info['used_disk'], disk_info['free_disk'], disk_info['disk_percent']))
        existing_disk_info = cursor.fetchone()

        if existing_disk_info is None:
            query_disk_info = """
            INSERT INTO disk_info (agent_id, total_disk, used_disk, free_disk, disk_percent)
            VALUES (%s, %s, %s, %s, %s)
            """
            disk_values = (agent_id, disk_info['total_disk'], disk_info['used_disk'], disk_info['free_disk'], disk_info['disk_percent'])
            cursor.execute(query_disk_info, disk_values)
            conn.commit()
            print("Yeni disk bilgisi eklendi.")
        else:
            print("Disk bilgisi zaten mevcut.")

        # OS bilgileri kontrol edilip ekleniyor
        os_info = data['os_info']
        cursor.execute("""
        SELECT id FROM os_info WHERE agent_id = %s AND os_name = %s AND os_version = %s
        AND os_release = %s
        """, (agent_id, os_info['os_name'], os_info['os_version'], os_info['os_release']))
        existing_os_info = cursor.fetchone()

        if existing_os_info is None:
            query_os_info = """
                INSERT INTO os_info (agent_id, os_name, os_version, os_release)
                VALUES (%s, %s, %s, %s)
            """
            os_values = (agent_id, os_info['os_name'], os_info['os_version'], os_info['os_release'])
            cursor.execute(query_os_info, os_values)
            conn.commit()
            print("Yeni OS bilgisi eklendi.")
        else:
            print("OS bilgisi zaten mevcut.")

        # Veritabanı bağlantısını kapat
        cursor.close()
        conn.close()

        return jsonify({"message": "Veri başarıyla alındı"}), 200

if __name__ == "__main__":
    app.run(host=config['server_host'], port=config['server_port'], debug=True)
