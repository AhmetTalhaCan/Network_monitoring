import json
import mysql.connector

# config.json dosyasından veritabanı bilgilerini yükleme
def load_config_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"Config dosyasını okuma hatası: {e}")
        return None

# JSON dosyasından verileri temizleme ve yükleme
def clean_json_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-16') as file:
            content = file.read()
            cleaned_content = content.replace('\ufeff', '')  # BOM temizleme
            return cleaned_content
    except Exception as e:
        print(f"Dosya okuma hatası: {e}")
        return None

def load_json_data(file_path):
    cleaned_content = clean_json_data(file_path)
    if cleaned_content is None:
        return None
    try:
        return json.loads(cleaned_content)
    except json.JSONDecodeError as e:
        print(f"JSON çözümleme hatası: {e}")
        return None

# Veritabanına bağlanma
def connect_to_db(config):
    try:
        connection = mysql.connector.connect(
            host=config["db_host"],
            port=config["db_port"],
            user=config["db_user"],
            password=config["db_password"],
            database=config["db_name"]
        )
        return connection
    except mysql.connector.Error as e:
        print(f"Veritabanına bağlanırken hata: {e}")
        return None

# Veritabanında son agent_id'yi al
def get_last_agent_id(connection):
    cursor = connection.cursor()
    
    # Son agent_id'yi alıyoruz
    query = "SELECT agent_id FROM agent ORDER BY agent_id DESC LIMIT 1"  # Son agent_id'yi alıyoruz
    cursor.execute(query)
    
    result = cursor.fetchone()
    cursor.close()
    
    if result:
        return result[0]  # agent_id'yi döndür
    return None  # Eğer bulunamazsa None döner

# Veritabanına veri ekleme
def insert_data_into_db(connection, merged_data):
    cursor = connection.cursor()
    insert_query = """
    INSERT INTO devices (name, mac_address, ip_address)
    VALUES (%s, %s, %s)
    """
    
    for item in merged_data:
        cursor.execute(insert_query, (item["name"], item["mac_address"], item["ip_address"]))
        
    connection.commit()
    print(f"{cursor.rowcount} satır başarıyla eklendi.")
    cursor.close()

# ip.json ve mac.json dosyalarını okuma
def read_and_merge_data():
    ip_data = load_json_data(r'C:\\Users\\canta\\Desktop\\Network_monitoring\\addUser\\ip.json')
    mac_data = load_json_data(r'C:\\Users\\canta\\Desktop\\Network_monitoring\\addUser\\mac.json')

    if ip_data and mac_data:
        print("Veriler başarılı bir şekilde okundu.")
    else:
        print("Veriler okunamadı.")
        return None

    # Ethernet ve Wi-Fi'yi seçmek için iki liste oluştur
    selected_ip = [item for item in ip_data if item['InterfaceAlias'] in ['Ethernet', 'Wi-Fi']]
    selected_mac = [item for item in mac_data if item['Name'] in ['Ethernet', 'Wi-Fi']]

    # Sonuçları birleştir
    merged_data = []
    for ip_item in selected_ip:
        for mac_item in selected_mac:
            if ip_item['InterfaceAlias'] == mac_item['Name']:
                merged_data.append({
                    "name": mac_item['Name'],
                    "mac_address": mac_item['MacAddress'],
                    "ip_address": ip_item['IPAddress']
                })

    return merged_data

# config.json dosyasını yükleme
config = load_config_data(r'C:\\Users\\canta\\Desktop\\Network_monitoring\\addUser\\config.json')

if config:
    merged_data = read_and_merge_data()
    if merged_data:
        # Veritabanına bağlanma
        db_connection = connect_to_db(config)
        if db_connection:
            # Verileri veritabanına ekleme
            insert_data_into_db(db_connection, merged_data)
            db_connection.close()
else:
    print("Config verisi okunamadı.")
