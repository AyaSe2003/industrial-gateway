import os
import platform
import subprocess

def test_cpu():
    """Afficher info CPU et cœurs"""
    print("=" * 50)
    print("INFORMATION CPU")
    print("=" * 50)
    
    # Nombre de cœurs
    cores = os.cpu_count()
    print(f"✓ Nombre de cœurs CPU: {cores}")
    
    # Architecture
    print(f"✓ Architecture: {platform.machine()}")
    
    # Fréquence CPU
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', 'r') as f:
            freq = int(f.read()) / 1000000
            print(f"✓ Fréquence actuelle: {freq:.2f} GHz")
    except:
        print("⚠️ Impossible de lire la fréquence CPU")

def test_memory():
    """Afficher la RAM disponible"""
    print("\n" + "=" * 50)
    print("MÉMOIRE")
    print("=" * 50)
    
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            if 'MemTotal' in line:
                mem = int(line.split()[1]) / 1024 / 1024
                print(f"✓ RAM totale: {mem:.2f} GB")
            elif 'MemAvailable' in line:
                mem = int(line.split()[1]) / 1024 / 1024
                print(f"✓ RAM disponible: {mem:.2f} GB")

def test_storage():
    """Afficher l'espace disque"""
    print("\n" + "=" * 50)
    print("STOCKAGE")
    print("=" * 50)
    
    stat = os.statvfs('/')
    free = (stat.f_bavail * stat.f_frsize) / (1024**3)
    total = (stat.f_blocks * stat.f_frsize) / (1024**3)
    print(f"✓ Espace total: {total:.1f} GB")
    print(f"✓ Espace libre: {free:.1f} GB")

def test_python_modules():
    """Vérifier les modules Python installés"""
    print("\n" + "=" * 50)
    print("MODULES PYTHON")
    print("=" * 50)
    
    modules = ['numpy', 'scipy', 'smbus2', 'fastapi', 'uvicorn']
    
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module} - installé")
        except ImportError:
            print(f"❌ {module} - MANQUANT")

def test_network():
    """Afficher l'adresse IP"""
    print("\n" + "=" * 50)
    print("RÉSEAU")
    print("=" * 50)
    
    result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
    ip = result.stdout.strip()
    print(f"✓ Adresse IP: {ip}")

if __name__ == "__main__":
    print("\n🔍 DIAGNOSTIC DU SYSTÈME - ODROID-N2+\n")
    
    test_cpu()
    test_memory()
    test_storage()
    test_python_modules()
    test_network()
    
    print("\n" + "=" * 50)
    print("✅ Diagnostic terminé")
    print("=" * 50)