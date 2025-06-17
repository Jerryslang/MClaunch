import os, random, json, subprocess
import zipfile, platform, threading, time 
import tomllib, hashlib
import tkinter as tk

from pathlib import Path

# TOML CONFIG
with open("config.toml", "rb") as f:
    try:
        config = tomllib.load(f)
    except Exception as e:
        print(f'Error: Config Error\n{e}')
        exit()

try: # requests lib check
    import requests
except ImportError:
    subprocess.run(["pip", "install", "requests"])
    print('(installed dependencies) please restart the script')
    time.sleep(1);exit()

try: # java install check
    subprocess.run(['java', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
except (subprocess.CalledProcessError, FileNotFoundError):
    raise RuntimeError('Java is required to run this script either its not installed or not added to your systems path. check the README.md for downloads')

# CONFIG
MClaunch_version = "1.1"
MC_VERSION = config["installer"]["version"] # tells the installer what version to install
INSTALL_DEBUG = False # dosent install assets for fast installs, if true (usefull for debugging)
BASE_DIR = os.path.join(Path(__file__).parent, "instances", MC_VERSION)
MAX_MEMORY = config["java"]["max_memory"]

LIB_DIR = os.path.join(BASE_DIR, "libraries")
NATIVES_DIR = os.path.join(BASE_DIR, "natives")
GAME_DIR = os.path.join(BASE_DIR, "game")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CLIENT_JAR = os.path.join(BASE_DIR, "client.jar")

USERNAME = config["runtime"]["username"]
UUID = config["runtime"]["uuid"]
ACCESSTOKEN = config["runtime"]["accesstoken"]
USERTYPE = config["runtime"]["usertype"]

SYSTEM = platform.system().lower()
IS_WINDOWS = SYSTEM == "windows"
IS_LINUX = SYSTEM == "linux"

print(f"""

MClaunch:
  MClaunch Version: {MClaunch_version}
  Minecraft Version: {MC_VERSION}

  Allocated Memory: {config["java"]["max_memory"]}

  USERNAME: {USERNAME}
  UUID: {UUID}
  USERTYPE: {USERTYPE}

""")

def log(text, text_box): # puts {text} in the tkinter {text_box}
    text_box.insert(tk.END, f'{text}\n')
    text_box.see(tk.END)

def download_file(url, dest):
    if not os.path.isfile(dest):
        log(f"Downloading {url} -> {dest}", text_box)
        r = requests.get(url, stream=True)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def extract_natives(zip_path, extract_to):
    log(f"Extracting natives from {zip_path}", text_box)
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)

def get_version_json_url(version_id):
    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    log(f"manifest: {manifest_url}", text_box)
    resp = requests.get(manifest_url)
    manifest = resp.json()
    for version in manifest["versions"]:
        if version["id"] == version_id:
            return version["url"]
    raise ValueError(f"Version '{version_id}' not found in manifest")

def download_assets(index_url, asset_index_id):
    index_path = os.path.join(ASSETS_DIR, "indexes", f"{asset_index_id}.json")
    download_file(index_url, index_path)

    with open(index_path, "r") as f:
        index_data = json.load(f)

    for asset_name, asset_info in index_data["objects"].items():
        hash_val = asset_info["hash"]
        subdir = hash_val[:2]
        object_url = f"https://resources.download.minecraft.net/{subdir}/{hash_val}"
        object_path = os.path.join(ASSETS_DIR, "objects", subdir, hash_val)
        download_file(object_url, object_path)

def main():
    if os.path.exists(CLIENT_JAR):
        log(f"Instance for version {MC_VERSION} already exists. Skipping installation.", text_box)
    else:
        os.makedirs(BASE_DIR, exist_ok=True)

        # get version metadata
        version_url = get_version_json_url(MC_VERSION)
        version_data = requests.get(version_url).json()

        # downloads client.jar
        client_info = version_data["downloads"]["client"]
        download_file(client_info["url"], CLIENT_JAR)

        # download libraries and natives
        for lib in version_data["libraries"]:
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                lib_path = os.path.join(LIB_DIR, artifact["path"])
                download_file(artifact["url"], lib_path)

            classifiers = lib.get("downloads", {}).get("classifiers")
            if classifiers:
                native_key = None
                if IS_WINDOWS and "natives-windows" in classifiers:
                    native_key = "natives-windows"
                elif IS_LINUX and "natives-linux" in classifiers:
                    native_key = "natives-linux"
                if native_key:
                    native_info = classifiers[native_key]
                    native_path = os.path.join(LIB_DIR, native_info["path"])
                    download_file(native_info["url"], native_path)
                    extract_natives(native_path, NATIVES_DIR)

    version_url = get_version_json_url(MC_VERSION)
    version_data = requests.get(version_url).json()

    jars = []
    for root, _, files in os.walk(LIB_DIR):
        for file in files:
            if file.endswith(".jar"):
                jars.append(os.path.join(root, file))
    jars.append(CLIENT_JAR)
    classpath = (";" if IS_WINDOWS else ":").join(jars)

    main_class = version_data["mainClass"]
    asset_index = version_data["assetIndex"]["id"]

    if INSTALL_DEBUG == False:
        asset_index_info = version_data["assetIndex"]
        asset_index_url = asset_index_info["url"]
        asset_index_id = asset_index_info["id"]
        download_assets(asset_index_url, asset_index_id)

    args = [
        "--username", USERNAME,
        "--version", MC_VERSION,
        "--gameDir", GAME_DIR,
        "--assetsDir", ASSETS_DIR,
        "--assetIndex", asset_index,
        "--uuid", UUID,
        "--accessToken", ACCESSTOKEN,
        "--userType", USERTYPE,
        "--versionType", "release",
        "--userProperties", "{}"
    ]

    java_cmd = [
        "java",
        f'-Xmx{config["java"]["max_memory"]}',
        f"-Djava.library.path={NATIVES_DIR}",
        "-cp", classpath,
        main_class,
    ] + args

    log("Launching Minecraft:", text_box)
    log(" ".join(java_cmd), text_box)
    proc = subprocess.Popen(
        java_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in proc.stdout:
        log(line.rstrip(), text_box)

class App:
    def __init__(self, root):
        self.root = root
        root.title("MClaunch")

        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)

        self.text_box = tk.Text(root, wrap='word')
        global text_box
        text_box = self.text_box
        self.text_box.grid(row=0, column=0, sticky='nsew')

        threading.Thread(target=main, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
