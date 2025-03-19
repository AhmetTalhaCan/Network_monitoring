import os
import platform
import psutil
import json
import subprocess
import requests
import time
from datetime import datetime, timedelta  # timedelta'ı doğru şekilde içe aktardık

# Yapılandırma dosyasını yükler
def load_config():
    config_file = "config.json"
    default_config = {
        "server_url": "http://127.0.0.1:8080/receive_device_info",  # Sunucu URL'si
        "agent_id": None  # Dinamik olarak belirlenecek
    }

    # Yapılandırma dosyasını oku veya oluştur
    if os.path.exists(config_file):
        with open(config_file, "r") as file:
            config = json.load(file)
    else:
        with open(config_file, "w") as file:
            json.dump(default_config, file, indent=4)
        config = default_config

    # agent_id her durumda dinamik olarak oluşturulsun
    config["agent_id"] = f"{platform.node()}-{os.getlogin()}"
    return config


# Sistemin genel bilgilerini toplar
def get_system_info():
    uname = platform.uname()
    system_info = {
        "system": uname.system,
        "node_name": uname.node,
        "release": uname.release,
        "version": uname.version,
        "machine": uname.machine,
        "processor": uname.processor
    }
    return system_info


# Bellek bilgilerini alır
def get_memory_info():
    memory = psutil.virtual_memory()
    return {
        "total_memory": memory.total,
        "available_memory": memory.available,
        "used_memory": memory.used,
        "memory_percent": memory.percent
    }


# CPU kullanım bilgisini alır
def get_cpu_info():
    cpu_percent = psutil.cpu_percent(interval=1)
    return {"cpu_percent": cpu_percent}


# Disk kullanım bilgilerini alır
def get_disk_info():
    disk = psutil.disk_usage('/')
    return {
        "total_disk": disk.total,
        "used_disk": disk.used,
        "free_disk": disk.free,
        "disk_percent": disk.percent
    }


# İşletim sistemi bilgilerini alır
def get_os_info():
    return {
        "os_name": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release()
    }

# Yüklü yazılımları ve sürümlerini listeler
def list_installed_software_with_version():
    installed_software = []
    
    # WMIC komutunu subprocess ile çalıştırıyoruz
    result = subprocess.run(['wmic', 'product', 'get', 'Name,Version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    
    # Çıktıyı alıyoruz
    output = result.stdout
    
    for line in output.splitlines():
        if line.strip():  # Boş satırları atlıyoruz
            software_info = line.split(None, 1)  # İki kısmı ayırmak için None kullanıyoruz
            if len(software_info) == 2:
                name, version = software_info
                installed_software.append((name, version))
    
    return installed_software


# Sistem çalışma süresini alır
def get_uptime():
    uptime_seconds = time.time() - psutil.boot_time()
    return str(timedelta(seconds=uptime_seconds))  # timedelta'ı doğru şekilde kullandık


# Sistemin açılış zamanını alır
def get_boot_time():
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    return boot_time.strftime("%Y-%m-%d %H:%M:%S")


# Verileri sunucuya gönderir
def send_data_to_server(data, server_url):
    try:
        response = requests.post(server_url, json=data)
        if response.status_code == 200:
            print(f"Veriler başarıyla sunucuya gönderildi: {response.status_code}")
        else:
            print(f"Sunucuya veri gönderimi başarısız oldu. Hata Kodu: {response.status_code}")
    except Exception as e:
        print(f"Sunucuya veri gönderirken hata oluştu: {str(e)}")


# Ajanı çalıştırır
def run_agent(config):
    # Sistemin bilgilerini toplar
    system_info = get_system_info()
    memory_info = get_memory_info()
    cpu_info = get_cpu_info()
    disk_info = get_disk_info()
    os_info = get_os_info()
    installed_software = list_installed_software_with_version()
    uptime = get_uptime()
    boot_time = get_boot_time()

    # Toplanan verileri hazırlar
    agent_data = {
        "agent_id": config["agent_id"],
        "system_info": system_info,
        "memory_info": memory_info,
        "cpu_info": cpu_info,
        "disk_info": disk_info,
        "os_info": os_info,
        "installed_software": installed_software,
        "uptime": uptime,
        "boot_time": boot_time
    }

    # Sunucuya veri gönderir
    send_data_to_server(agent_data, config["server_url"])


# Ana program döngüsü
def main():
    config = load_config()
    run_agent(config)

if __name__ == "__main__":
    main()