import requests
from urllib.parse import quote
import time
import os
import re
import sys
import platform
import shutil
# ── Classe UI ─────────────────────────────────────────────────────────────────
class UI:
    @staticmethod
    def info(msg):    print(f"ℹ️  {msg}")
    @staticmethod
    def success(msg): print(f"✅ {msg}")
    @staticmethod
    def error(msg):   print(f"❌ {msg}")
    @staticmethod
    def warn(msg):    print(f"⚠️  {msg}")

# ── Domaine actif ─────────────────────────────────────────────────────────────
def verify_domain_redirect(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.head(url, timeout=10, headers=headers, allow_redirects=True)
        final_url = response.url
        if "anime-sama" in final_url and "anime-sama.pw" not in final_url:
            return True, final_url
        return False, final_url
    except Exception:
        return False, None

def get_active_domain():
    try:
        UI.info("Recherche du serveur actif...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get("https://anime-sama.pw/", timeout=10, headers=headers)
        if response.status_code == 200:
            pattern = r'<a\s+class="btn-primary"\s+href="(https?://anime-sama\.[a-z]+)"'
            match = re.search(pattern, response.text)
            if match:
                base_domain = match.group(1)
                is_valid, redirected_url = verify_domain_redirect(base_domain)
                if is_valid:
                    redirected_domain = redirected_url.split("/catalogue")[0] if "/catalogue" in redirected_url else redirected_url.rstrip("/")
                    UI.success("Serveur actif trouvé.")
                    return f"{redirected_domain}/catalogue/"
            pattern_fallback = r'href="(https?://anime-sama\.(?!pw)[a-z]+)"'
            match_fallback = re.search(pattern_fallback, response.text)
            if match_fallback:
                base_domain = match_fallback.group(1)
                is_valid, redirected_url = verify_domain_redirect(base_domain)
                if is_valid:
                    redirected_domain = redirected_url.split("/catalogue")[0] if "/catalogue" in redirected_url else redirected_url.rstrip("/")
                    UI.success(f"Serveur actif trouvé : {redirected_domain}")
                    return f"{redirected_domain}/catalogue/"
        UI.error("Impossible de trouver le serveur actif.")
        UI.warn("Fermeture automatique dans 10 secondes...")
        time.sleep(10)
        sys.exit(1)
    except Exception as e:
        UI.error(f"Erreur lors de la récupération du serveur : {e}")
        UI.warn("Fermeture automatique dans 10 secondes...")
        time.sleep(10)
        sys.exit(1)

def check_domain_availability():
    return get_active_domain()

def find_last_downloaded_chapter(folder_path):
    """Trouve le dernier chapitre téléchargé dans le dossier"""
    if not os.path.exists(folder_path):
        return None
    
    chapters = []
    
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path):
            # Pattern pour matcher les dossiers de chapitres (ex: "Chapitre_1", "Chapitre_25")
            match = re.match(r'Chapitre[_\s]?(\d+)', item, re.IGNORECASE)
            if match:
                chapter_num = int(match.group(1))
                chapters.append(chapter_num)
    
    if not chapters:
        return None
    
    chapters.sort(reverse=True)
    return chapters[0]

def count_images_in_chapter(folder_path, chapter_num):
    """Compte le nombre d'images téléchargées pour un chapitre"""
    chapter_folder = os.path.join(folder_path, f"Chapitre_{chapter_num}")
    
    if not os.path.exists(chapter_folder):
        return 0
    
    files = os.listdir(chapter_folder)
    # Compter uniquement les fichiers .jpg
    return len([f for f in files if f.endswith('.jpg')])

def get_total_pages_for_chapter(base_url, chapter):
    """Récupère le nombre total de pages pour un chapitre"""
    count = 0
    for page in range(1, 1000):
        image_url = f"{base_url}/{chapter}/{page}.jpg"
        try:
            response = requests.head(image_url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                count += 1
            else:
                break
        except:
            break
        time.sleep(0.2)
    return count

def check_image_exists(url):
    """Vérifie si une image existe"""
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def check_disk_space(min_gb=1):
    s = platform.system()
    
    if s == "Windows":
        total, used, free = shutil.disk_usage("C:\\")
        free_space_gb = free / (1024**3)
        
    elif s == "Linux" and "ANDROID_STORAGE" in os.environ:
        try:
            output = os.popen("df -h /storage/emulated/0").read()
            lines = output.split("\n")
            if len(lines) > 1:
                free_space = lines[1].split()[3]
                if "G" in free_space:
                    free_space_gb = float(free_space.replace("G", ""))
                elif "M" in free_space:
                    free_space_gb = float(free_space.replace("M", "")) / 1024
                else:
                    free_space_gb = 0
            else:
                free_space_gb = 0
        except:
            free_space_gb = 0
    else:
        statvfs = os.statvfs("/")
        free_space_gb = (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
    
    return free_space_gb >= min_gb

def download_image(url, filepath):
    """Télécharge une image"""
    if not check_disk_space(0.1):
        print("⛔ Espace disque insuffisant.")
        return False
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"      ❌ Erreur: {e}")
    return False

def find_working_server(manga_name, manga_url, domain, max_servers=10):
    """Trouve le serveur fonctionnel"""
    domain = domain.rstrip("/")
    print(f"🔍 Recherche du serveur fonctionnel...", end=" ", flush=True)
    
    found_versions = []  # Liste des versions trouvées
    tested = []          # Pour afficher les échecs seulement si tout échoue
    
    # Liste des variantes à tester
    variants = [
        ("normal", manga_name, manga_url),
        ("normal", manga_name.title(), quote(manga_name.title())),
    ]
    
    for version_type, variant_name, variant_url in variants:
        for server_num in range(1, max_servers + 1):
            server = f"s{server_num}"
            test_url = f"{domain}/{server}/scans/{variant_url}/1/1.jpg"
            tested.append((server, test_url))
            
            if check_image_exists(test_url):
                print("✅")
                found_versions.append(("Normal", server, variant_url))
                break
            
            time.sleep(0.5)
        
        if found_versions:
            break
    
    # Tester aussi avec " Couleur" (sans afficher les messages)
    couleur_variants = [
        quote(manga_name + " Couleur"),
        quote(manga_name.title() + " Couleur"),
    ]
    
    for manga_url_with_color in couleur_variants:
        for server_num in range(1, max_servers + 1):
            server = f"s{server_num}"
            test_url = f"{domain}/{server}/scans/{manga_url_with_color}/1/1.jpg"
            
            if check_image_exists(test_url):
                found_versions.append(("Couleur", server, manga_url_with_color))
                break
            
            time.sleep(0.3)
        
        if len(found_versions) > 1:
            break
    
    # Si aucune version trouvée : afficher tous les échecs
    if not found_versions:
        print("❌")
        print("\n⚠️  Détail des serveurs testés :")
        for srv, url in tested:
            print(f"   ❌ {srv} → {url}")
        print("\n❌ Aucun serveur fonctionnel trouvé!")
        return None, None
    
    # Si une seule version trouvée, la retourner directement
    if len(found_versions) == 1:
        return found_versions[0][1], found_versions[0][2]
    
    # Si plusieurs versions trouvées, demander à l'utilisateur
    print(f"\n{'='*60}")
    print("📚 Plusieurs versions disponibles :")
    print(f"{'='*60}")
    for i, (version_name, server, url) in enumerate(found_versions, 1):
        print(f"{i}. {version_name} (serveur {server})")
    print()
    
    while True:
        try:
            choice = input("Choisissez la version (1 ou 2): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(found_versions):
                selected = found_versions[choice_num - 1]
                print(f"\n✅ Version '{selected[0]}' sélectionnée!\n")
                return selected[1], selected[2]
            else:
                print("❌ Choix invalide, réessayez.")
        except ValueError:
            print("❌ Veuillez entrer un nombre valide.")
        except KeyboardInterrupt:
            print("\n\n❌ Annulé par l'utilisateur.")
            return None, None

def get_download_path():
    s = platform.system()
    if s == "Windows":
        return os.path.join(os.getcwd())
    elif s == "Linux" and "ANDROID_STORAGE" in os.environ:
        return "/storage/emulated/0/Download/Scan"
    else:
        print("Ce script ne fonctionne que sous Windows ou Android.")
        exit(1)

def download_manga(manga_name, start_chapter=None):
    """
    Télécharge un manga depuis anime-sama.fr
    
    Args:
        manga_name: Nom du manga (ex: "La Nuit des Démons")
        start_chapter: Chapitre de départ (None = auto-détection)
    """
    s = platform.system()
    is_android = s == "Linux" and "ANDROID_STORAGE" in os.environ
    
    if not is_android:
        if s == "Windows":
            os.system(f'title Co-Sama : {manga_name}')
        elif s == "Linux":
            sys.stdout.write(f"\033]0;Co-Sama : {manga_name}\007")
            sys.stdout.flush()
    
    # Créer le dossier principal du manga
    manga_folder_name = manga_name.replace(" ", "_")
    manga_folder = os.path.join(get_download_path(), manga_folder_name)
    os.makedirs(manga_folder, exist_ok=True)
    
    if not check_disk_space():
        print("⛔ Espace disque insuffisant. Libérez de l'espace et réessayez.")
        return
    
    # Récupérer le domaine actif scrappé
    active_catalogue = get_active_domain()
    domain = active_catalogue.replace("/catalogue/", "").replace("/catalogue", "")

    # Encoder le nom pour l'URL
    manga_url = quote(manga_name)
    
    # Trouver le serveur fonctionnel
    result = find_working_server(manga_name, manga_url, domain)
    if result[0] is None:
        print("\n❌ Aucun serveur fonctionnel trouvé!")
        return
    
    server, final_manga_url = result
    base_url = f"{domain}/{server}/scans/{final_manga_url}"
    
    # Déterminer le chapitre de départ
    if start_chapter is None:
        last_chapter = find_last_downloaded_chapter(manga_folder)
        if last_chapter:
            # Vérifier si le dernier chapitre est complet
            downloaded_pages = count_images_in_chapter(manga_folder, last_chapter)
            total_pages = get_total_pages_for_chapter(base_url, last_chapter)
            
            if downloaded_pages < total_pages:
                print(f"\n📖 Reprise du Chapitre {last_chapter} ({downloaded_pages}/{total_pages} pages)")
                start_chapter = last_chapter
            else:
                print(f"\n📖 Dernier chapitre complet: {last_chapter}")
                start_chapter = last_chapter + 1
        else:
            print("\n📖 Aucun chapitre téléchargé, démarrage depuis le début")
            start_chapter = 1
    
    print(f"\n{'='*60}")
    print(f"📚 Téléchargement de '{manga_name}'")
    print(f"🌐 Serveur: {server}")
    print(f"📍 Départ: Chapitre {start_chapter}")
    print(f"{'='*60}\n")
    
    # Télécharger les chapitres
    chapter = start_chapter
    consecutive_failures = 0
    
    while consecutive_failures < 3:  # Arrêt après 3 chapitres non trouvés
        chapter_folder = os.path.join(manga_folder, f"Chapitre_{chapter}")
        os.makedirs(chapter_folder, exist_ok=True)
        
        print(f"📖 Chapitre {chapter}:")
        
        # Vérifier combien de pages sont déjà téléchargées
        existing_pages = count_images_in_chapter(manga_folder, chapter)
        start_page = existing_pages + 1 if existing_pages > 0 else 1
        
        if start_page > 1:
            print(f"   ℹ️  Reprise à la page {start_page}")
        
        pages_downloaded = 0
        page = start_page
        
        while True:
            image_url = f"{base_url}/{chapter}/{page}.jpg"
            image_path = os.path.join(chapter_folder, f"{page}.jpg")
            
            # Vérifier si l'image existe déjà
            if os.path.exists(image_path):
                print(f"   ⏭️  Page {page} (déjà téléchargée)")
                page += 1
                pages_downloaded += 1
                continue
            
            # Vérifier si l'image existe en ligne
            if not check_image_exists(image_url):
                if page == 1:
                    print(f"   ❌ Chapitre {chapter} non trouvé")
                    consecutive_failures += 1
                else:
                    total_pages = existing_pages + pages_downloaded
                    print(f"   ✅ Chapitre {chapter} terminé: {total_pages} pages\n")
                    consecutive_failures = 0
                break
            
            # Télécharger l'image
            print(f"   ⬇️  Page {page}...", end=" ")
            if download_image(image_url, image_path):
                print("✓")
                pages_downloaded += 1
            else:
                print("✗")
                break
            
            page += 1
            time.sleep(0.3)  # Pause pour ne pas surcharger le serveur
        
        if consecutive_failures >= 3:
            print(f"\n🏁 Fin du téléchargement (3 chapitres consécutifs non trouvés)")
            break
        
        chapter += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Téléchargement terminé!")
    print(f"📁 Dossier: {manga_folder}")
    print(f"{'='*60}")

# Co-sama - Téléchargeur de manga
if __name__ == "__main__":
    s = platform.system()
    is_android = s == "Linux" and "ANDROID_STORAGE" in os.environ

    if s == "Windows":
        os.system(f'title Co-Sama')
    elif s == "Linux" and not is_android:
        sys.stdout.write(f"\033]0;Co-Sama\007")
        sys.stdout.flush()

    print("="*60)
    print("🌙 CO-SAMA - Téléchargeur de Manga 🌙")
    print("="*60)
    print()

    try:
        manga_name = input("📚 Entrez le nom du manga: ").strip()

        if not manga_name:
            print("❌ Nom de manga invalide!")
        else:
            manga_name = manga_name.title()
            print()
            download_manga(manga_name)

    except KeyboardInterrupt:
        print("\n\n⚠️  Arrêté par l'utilisateur.")
