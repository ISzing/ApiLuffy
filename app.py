from flask import Flask, request, jsonify, send_from_directory, render_template,Response, stream_with_context
from flask_cors import CORS # type: ignore
from wsgiref.util import FileWrapper
from werkzeug.wsgi import wrap_file
import os
import asyncio
import base64
from playwright.async_api import async_playwright # type: ignore
from urllib.parse import unquote
from flask import send_file
import glob
from playwright.async_api import async_playwright # type: ignore
from functools import lru_cache
import time
import re
import mimetypes
async def scrape_episodes(url):
    episodes = []
    if "/series/" in url:
        folder_name = url.split("/series/")[1].split("/")[0]
    elif "/titles/" in url:
        folder_name = url.split("/titles/")[1].split("/")[0]
    else:
        raise ValueError("URL nie zawiera '/series/' ani '/titles/'")
    scraped_folder = os.path.join(BASE_DIR, folder_name)
    if not os.path.exists(scraped_folder):
        os.makedirs(scraped_folder)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        try:
            await page.click('button.qxOn2zvg.e1sXLPUy', timeout=3000)
            await page.wait_for_timeout(500)
        except Exception as e:
            print("Przycisk 'Zaakceptuj wszystko' nie został znaleziony:", e)
        try:
            await page.click('a.cb-enable', timeout=3000)
            await page.wait_for_timeout(500)
        except Exception as e:
            print("Link 'Akceptuję' nie został znaleziony:", e)
        try:
            await page.click('a.login_form_open.top-button', timeout=3000)
        except Exception as e:
            print("Nie udało się znaleźć przycisku 'Logowanie':", e)
            await browser.close()
            return [], []
        try:
            await page.wait_for_selector('input[name="username"]:visible', timeout=1000)
            await page.fill('input[name="username"]', "iszingo2")
            await page.wait_for_selector('input[name="password"]:visible', timeout=1000)
            await page.fill('input[name="password"]', "Kacper12")
            await page.click('button[type="submit"]')
        except Exception as e:
            print(f"Błąd logowania: {e}")
            await browser.close()
            return [], []
        url = url.replace("episodes", "all-episodes");
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector("table", timeout=1000)
        rows = await page.locator("table.data-view-table-big.data-view-table-episodes tbody.list-episode-checkboxes tr").all()
        for row in rows:
            episode_number = await row.locator("td").first.inner_text()
            details_button = row.locator("td.button-group a.button.active.detail")
            href = await details_button.get_attribute("href")
            if href and "/view/" in href:
                episode_id = href.split("/")[-1]
                episodes.append(f"{episode_number}  {episode_id}")
        await browser.close()
    return folder_name, episodes
app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",  
            "http://localhost:5000",
            "http://localhost:8000",    
            "https://9wq94rgh-5000.euw.devtunnels.ms"  # Usuń ostatni "/"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
BASE_DIR = "scraped_data"
@app.route('/')
def home():
    return render_template('index.html')
@app.route('/download')
def download():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    exe_files = [f for f in os.listdir(current_dir) if f.endswith('.exe')]
    
    if not exe_files:
        return {'error': 'No executable files found'}, 404
        
    newest_exe = max(
        exe_files,
        key=lambda f: os.path.getmtime(os.path.join(current_dir, f))
    )
    
    file_path = os.path.join(current_dir, newest_exe)
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=newest_exe,
        mimetype='application/octet-stream',
        max_age=0
    )
APP_FOLDER = "build"
@app.route("/<path:filename>")
def files(filename):
    return send_from_directory(APP_FOLDER, filename)
@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")
@app.route('/favicon.ico')
def icon():
    return send_from_directory(os.path.join(app.root_path, ''), 'favicon.ico', mimetype='image/vnd.microsoft.icon')
def get_txt_files_in_folder(base_path):
    txt_files = []
    for root, dirs, files in os.walk(base_path):
        for filename in files:
            if filename.endswith('.txt'):
                full_path = os.path.join(root, filename)
                relative_path = os.path.relpath(full_path, base_path)
                txt_files.append({
                    'name': filename,
                    'path': relative_path.replace('\\', '/'),
                    'subfolder': os.path.dirname(relative_path).replace('\\', '/')
                })
    return txt_files
def save_image(image_data, save_path):
    try:
        print(f"Zapisywanie obrazu do: {save_path}")  # DEBUG
        if image_data.startswith('data:image/png;base64,'):
            image_data = image_data.split(",")[1]
        image_bytes = base64.b64decode(image_data)
        folder = os.path.dirname(save_path)
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Utworzono folder: {folder}")  # DEBUG
        with open(save_path, 'wb') as f:
            f.write(image_bytes)
            print(f"Obraz zapisany: {save_path}")  # DEBUG
    except Exception as e:
        print(f"Błąd podczas zapisywania: {e}")  # DEBUG
@app.route('/folders', methods=['GET'])
async def list_folders():
    folders = await asyncio.to_thread(lambda: [f for f in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, f))])
    return jsonify({"folders": folders})
@app.route('/files/<folder_name>', methods=['GET'])
def list_files(folder_name):
    folder_path = os.path.join(BASE_DIR, folder_name)
    if not os.path.exists(folder_path):
        return jsonify({"error": "Folder nie istnieje"}), 404
    txt_files = get_txt_files_in_folder(folder_path)
    return jsonify({"files": txt_files})
@app.route('/adas/<path:folder_path>', methods=['GET'])
def get_fie(folder_path):
    try:
        folder_path = unquote(folder_path)
        full_folder_path = os.path.join(BASE_DIR, folder_path)
        search_pattern = os.path.join(full_folder_path, 'Odc*.txt')
        files = glob.glob(search_pattern)
        
        if not files:
            return jsonify({"error": "Brak plików .txt w folderze"}), 404
        
        # Get the current episode number from the first file found
        current_file = files[0]
        current_file_name = os.path.basename(current_file)
        match = re.search(r'Odc(\d+)\.txt', current_file_name)
        current_episode = int(match.group(1)) if match else None
        
        # First try to get skip and polskip from the current file
        with open(current_file, 'r', encoding='utf-8') as f:
            content = f.readlines()
        
        data = {}
        for line in content:
            if line.startswith("skip="):
                data["skip"] = line.strip().split("=")[1]
            elif line.startswith("polskip="):
                data["polskip"] = line.strip().split("=")[1]
        
        # If we have both values in the current file, return them
        if "skip" in data and "polskip" in data:
            return jsonify(data)
        
        # If we're missing values and we have a valid episode number greater than 1
        if current_episode and current_episode > 1:
            # Split the path to get the anime and move up one level
            path_parts = folder_path.split('/')
            if len(path_parts) > 1:
                # Get the anime base directory (the first part of the path)
                anime_base_dir = path_parts[0]
                anime_full_path = os.path.join(BASE_DIR, anime_base_dir)
                
                # Look for the previous episode file in all subdirectories of the anime
                prev_episode_name = f'Odc{current_episode-1}.txt'
                
                # Traverse all subdirectories in the anime directory
                for root, dirs, files in os.walk(anime_full_path):
                    for file in files:
                        if file == prev_episode_name:
                            prev_episode_file = os.path.join(root, file)
                            
                            # Found the previous episode file, try to get skip and polskip from it
                            with open(prev_episode_file, 'r', encoding='utf-8') as f:
                                content = f.readlines()
                            
                            data = {}
                            for line in content:
                                if line.startswith("skip="):
                                    data["skip"] = line.strip().split("=")[1]
                                elif line.startswith("polskip="):
                                    data["polskip"] = line.strip().split("=")[1]
                            
                            if "skip" in data and "polskip" in data:
                                return jsonify(data)
                            
                            # If we found the file but it didn't have the values, break the loop
                            # as we're looking for a specific named file regardless of content
                            break
        
        # If we get here, no valid skip and polskip values were found
        return jsonify({"error": "Brak wymaganych wartości skip i polskip w plikach"}), 404
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/adas/<path:folder_path>', methods=['POST'])
def save_fie(folder_path):
    try:
        folder_path = unquote(folder_path)
        full_folder_path = os.path.join(BASE_DIR, folder_path)
        if not os.path.exists(full_folder_path):
            os.makedirs(full_folder_path)
        search_pattern = os.path.join(full_folder_path, 'Odc*.txt')
        files = glob.glob(search_pattern)
        file_path = files[0] if files else os.path.join(full_folder_path, "Odc1.txt")
        new_skip = request.json.get("skip")
        new_polskip = request.json.get("polskip")
        content = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        content[key] = value
        if new_skip is not None:
            content["skip"] = str(new_skip)
        if new_polskip is not None:
            content["polskip"] = str(new_polskip)
        with open(file_path, 'w', encoding='utf-8') as f:
            for key, value in content.items():
                f.write(f"{key}={value}\n")
        return jsonify({"message": "Dane zapisane poprawnie", "file": file_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/files/<path:file_path>', methods=['GET'])
def get_file(file_path):
    try:
        file_path = unquote(file_path)  # Dekodowanie URL
        full_path = os.path.join(BASE_DIR, file_path)
        if not os.path.isfile(full_path):
            return jsonify({"error": "Plik nie istnieje"}), 404
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/screenshot/<path:file_path>', methods=['GET'])
async def get_screenshot(file_path):
    full_path = os.path.join(BASE_DIR, file_path)
    if not os.path.exists(full_path):
        return jsonify({"error": "Plik nie istnieje"}), 404
    return await asyncio.to_thread(send_file, full_path, mimetype='image/png')
@app.route('/save/<path:filename>', methods=['POST'])
def save_file(filename):
    try:
        data = request.json  # Pobranie danych z requesta
        content = data.get("content", "")
        file_dir = os.path.dirname(filename)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir)
        with open(filename, "w", encoding="utf-8") as file:
            file.write(content)
        return jsonify({"message": "Plik zapisany pomyślnie"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/get_image/<path:folder_path>/<filename>', methods=['GET'])
def get_image(folder_path, filename):
    try:
        parts = folder_path.strip('/').split('/')
        if len(parts) < 2:
            return jsonify({"error": "Nieprawidłowa ścieżka folderu", "folder_path": folder_path}), 400
        main_folder = parts[0]  # np. '12434-hunter-x-hunter-2011'
        episode_folder = parts[1]  # np. '96812'
        base_folder = os.path.join("Scraped_data", main_folder)
        requested_folder = os.path.join(base_folder, episode_folder)
        episode_number = None
        if not os.path.isdir(requested_folder):
            return jsonify({"error": "Folder nie istnieje", "folder": requested_folder}), 404
        all_files = os.listdir(requested_folder)
        txt_files = [f for f in all_files if f.lower().startswith("odc") and f.lower().endswith(".txt")]
        for txt_file in txt_files:
            try:
                episode_number = int(txt_file[3:-4])
                break
            except ValueError:
                continue
        if episode_number is None:
            return jsonify({"error": "Nie znaleziono numeru odcinka", "files_in_folder": all_files}), 404
        file_path = os.path.join(requested_folder, filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='image/png')
        previous_folder = None
        for subfolder in sorted(os.listdir(base_folder)):
            subfolder_path = os.path.join(base_folder, subfolder)
            if os.path.isdir(subfolder_path):
                txt_files = [f for f in os.listdir(subfolder_path) if f.lower().startswith("odc") and f.lower().endswith(".txt")]
                for txt_file in txt_files:
                    try:
                        prev_episode_id = int(txt_file[3:-4])
                        if prev_episode_id == episode_number - 1:
                            previous_folder = subfolder_path
                            break
                    except ValueError:
                        continue
            if previous_folder:
                break
        if previous_folder:
            fallback_file_path = os.path.join(previous_folder, filename)
            if os.path.exists(fallback_file_path):
                return send_file(fallback_file_path, mimetype='image/png')
            else:
                return jsonify({"error": "Nie znaleziono pliku w poprzednim folderze", "previous_folder": previous_folder, "filename": filename}), 404
        return jsonify({"error": "Plik nie istnieje", "searched_folders": [requested_folder, previous_folder]}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response
@app.route('/save_screenshot/<path:folderpath>', methods=['POST'])
def save_screenshot(folderpath):
    if 'file1' not in request.files or 'file2' not in request.files:
        return jsonify({"error": "Brak wymaganych plików"}), 400
    file1 = request.files['file1']
    file2 = request.files['file2']
    save_path = os.path.join("scraped_data", folderpath)
    os.makedirs(save_path, exist_ok=True)
    print(f"Ścieżka zapisu: {save_path}")  # Logowanie ścieżki zapisu
    file1_path = os.path.join(save_path, "intro_screenshot1.png")
    file1.save(file1_path)
    file2_path = os.path.join(save_path, "intro_screenshot2.png")
    file2.save(file2_path)
    return jsonify({"message": "Pliki zostały przesłane", "path": save_path, "file1": file1_path, "file2": file2_path})
@lru_cache(maxsize=50000)
def cached_screenshots(full_path):
    try:
        start_time = time.time()
        screenshots = [
            {'name': entry.name, 'path': os.path.relpath(entry.path, BASE_DIR).replace('\\', '/')}
            for entry in os.scandir(full_path)
            if entry.is_file() and (entry.name.endswith('_screenshot1.png') or entry.name.endswith('_screenshot2.png'))
        ]
        return screenshots
    except Exception as e:
        return {"error": str(e)}
@app.route('/check_screenshots/<path:folder_path>', methods=['GET'])
async def check_screenshots(folder_path):
    full_path = os.path.join(BASE_DIR, folder_path)
    if not os.path.exists(full_path):
        return jsonify({"error": "Folder nie istnieje"}), 404
    screenshots = await asyncio.to_thread(cached_screenshots, full_path)
    return jsonify({"screenshots": screenshots})
async def scrape_episodess(url):
    episodes = []
    if "/series/" in url:
        folder_name = url.split("/series/")[1].split("/")[0]
    elif "/titles/" in url:
        folder_name = url.split("/titles/")[1].split("/")[0]
    elif "/episode/" in url:
        folder_name = url.split("/episode/")[1].split("/")[0]
    elif "/all-episode/" in url:
        folder_name = url.split("/all-episode/")[1].split("/")[0]
    else:
        raise ValueError("URL nie zawiera '/series/' ani '/titles/'")
    scraped_folder = os.path.join(BASE_DIR, folder_name)
    if not os.path.exists(scraped_folder):
        os.makedirs(scraped_folder)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        ad_domains = ["doubleclick.net", "ads.google.com", "adservice.google.com"]
        async def intercept_request(route, request):
            if any(domain in request.url for domain in ad_domains):
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", intercept_request)
        ad_block_script = """
        document.addEventListener('DOMContentLoaded', function() {
            let adSelectors = [
                'iframe[title*="advertisement"]', 
                'div[class*="ad"]',
                'div[class*="popup"]', 
                'div[class*="overlay"]', 
                'div[class*="modal"]', 
                'div[class*="fullpage-ad"]'
            ];
            adSelectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => el.remove());
            });
            let closeButtons = ['button[class*="close"]', 'button[class*="dismiss"]', 'div[class*="close"]'];
            closeButtons.forEach(selector => {
                document.querySelectorAll(selector).forEach(btn => btn.click());
            });
        });
        """
        await page.add_init_script(ad_block_script)
        page.on("popup", lambda popup: popup.close())
        await page.goto(url, wait_until="domcontentloaded")
        viewport_size = await page.evaluate('''() => {
            return {
                width: window.innerWidth,
                height: window.innerHeight
            }
        }''')
        width = viewport_size['width']
        height = viewport_size['height']
        await page.mouse.click(width // 2, height // 2)
        try:
            await page.click('button.qxOn2zvg.e1sXLPUy', timeout=3000)
            await page.wait_for_timeout(500)
        except Exception as e:
            print("Przycisk 'Zaakceptuj wszystko' nie został znaleziony:", e)
        try:
            await page.click('a.cb-enable', timeout=3000)
            await page.wait_for_timeout(500)
        except Exception as e:
            print("Link 'Akceptuję' nie został znaleziony:", e)
        try:
            await page.click("body > div.l-global-width.l-container-primary > div > nav > ul > li:nth-child(2) > a")
            await page.wait_for_timeout(500)
        except Exception as e:
            print("Nie udało się kliknąć nawigacji przed logowaniem:", e)
        try:
            await page.click('a.login_form_open.top-button', timeout=2000)
        except Exception as e:
            print("Nie udało się znaleźć przycisku 'Logowanie':", e)
            await browser.close()
            return [], []
        try:
            await page.wait_for_selector('input[name="username"]:visible', timeout=1000)
            await page.fill('input[name="username"]', "iszingo2")
            await page.wait_for_selector('input[name="password"]:visible', timeout=1000)
            await page.fill('input[name="password"]', "Kacper12")
            await page.click('button[type="submit"]')
        except Exception as e:
            print(f"Błąd logowania: {e}")
            await browser.close()
            return [], []
        url = url.replace("episodes", "all-episodes");
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector("table", timeout=1000)
        rows = await page.locator("table.data-view-table-big.data-view-table-episodes tbody.list-episode-checkboxes tr").all()
        for row in rows:
            episode_number = await row.locator("td").first.inner_text()
            details_button = row.locator("td.button-group a.button.active.detail")
            href = await details_button.get_attribute("href")
            if href and "/view/" in href:
                episode_id = href.split("/")[-1]
                episodes.append(f"{episode_number}  {episode_id}")
        await browser.close()
    return folder_name, episodes
@app.route('/scrapee', methods=['POST'])
def scrapee():
    url = request.form['url']
    folder_name, episodes = asyncio.run(scrape_episodess(url))
    if not episodes:
        return jsonify({"error": "Brak danych do pobrania."}), 400
    folder_path = os.path.join(BASE_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    for episode in episodes:
        episode_id = episode.split()[-1]  # Pobierz ID odcinka z ostatniego elementu stringa
        episode_folder_path = os.path.join(folder_path, episode_id)
        os.makedirs(episode_folder_path, exist_ok=True)
        episode_number = episode.split()[0]  # Pobierz numer odcinka
        txt_file_path = os.path.join(episode_folder_path, f"Odc{episode_number}.txt")
        with open(txt_file_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(f"Odcinek {episode_number} - ID: {episode_id}\n")
            txt_file.write(f"FolderPath: /{folder_name}/{episode_id}")
    return jsonify({"folder_name": folder_name, "episodes": episodes})
@app.route('/check_path', methods=['GET'])
def check_path():
    path = request.args.get('path')
    if not path:
        return jsonify({"error": "Brak ścieżki w zapytaniu"}), 400
    full_path = os.path.join(BASE_DIR, path)
    exists = os.path.exists(full_path)
    return jsonify({"path": path, "exists": exists})
@app.route('/scrape', methods=['POST'])
def scrape():
    url = request.form['url']
    folder_name, episodes = asyncio.run(scrape_episodes(url))
    if not episodes:
        return jsonify({"error": "Brak danych do pobrania."}), 400
    folder_path = os.path.join(BASE_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    for episode in episodes:
        episode_id = episode.split()[-1]  # Pobierz ID odcinka z ostatniego elementu stringa
        episode_folder_path = os.path.join(folder_path, episode_id)
        os.makedirs(episode_folder_path, exist_ok=True)
        episode_number = episode.split()[0]  # Pobierz numer odcinka
        txt_file_path = os.path.join(episode_folder_path, f"Odc{episode_number}.txt")
        with open(txt_file_path, 'w', encoding='utf-8') as txt_file:
            txt_file.write(f"Odcinek {episode_number} - ID: {episode_id}\n")
            txt_file.write(f"FolderPath: /{folder_name}/{episode_id}")
    return jsonify({"folder_name": folder_name, "episodes": episodes})
if __name__ == '__main__':
    os.makedirs(BASE_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, ssl_context=None)
