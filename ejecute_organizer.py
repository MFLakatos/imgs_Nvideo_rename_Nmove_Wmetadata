
import os
import sys
import yaml
import pprint
import logging
from src.media_organizer import MediaOrganizer

# TODO: Cambiar el path para que funcione desde el yaml
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("logs/ejecute_organizer.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def load_config(path_to_yaml):
    with open(path_to_yaml, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def main():
    config = load_config("configs/settings.yaml")

    print_config(config)

    logging.info(f"Working directory: {os.getcwd()}")
    organizer = MediaOrganizer(config)
    organizer.check_already_processed_in_input()
    organizer.rename_and_copy_media()

    if config.get('inspect_some_files', False):
        n = config.get('number_of_files_to_inspect', 3)
        organizer.inspect_metadata(n)

    

def print_config(config: dict) -> None:
    print("\n📦 CONFIGURACIÓN DEL PROYECTO: MEDIA ORGANIZER")
    print("👤 Autor: Matías Fernández Lakatos\n")

    print("🔧 Rutas y parámetros principales:")
    print(f"   📂 Carpeta de entrada        : {config['input_dir']}")
    print(f"   📁 Carpeta de salida         : {config['output_dir']}")
    print(f"   🧰 Ruta FFmpeg               : {config['ffmpeg_path']}")
    print(f"   🧪 Ruta FFprobe              : {config['ffprobe_path']}")
    print(f"   🔑 Archivo .env              : {config['env_file']}")
    print(f"   📝 Log de procesados         : {config['log_file']}")
    print(f"   🔄 Máx. por sesión           : {config['max_files_per_session']}")
    print(f"   ❌ Eliminar tras procesar    : {config['delete_after_processing']}")

    log_conf = config.get('logging', {})
    print("\n🧾 Configuración del log:")
    print(f"   ✅ Logging activado          : {log_conf.get('enabled', False)}")
    print(f"   📄 Archivo de log            : {log_conf.get('log_file', 'media_organizer.log')}")
    print(f"   📊 Nivel de log              : {log_conf.get('log_level', 'INFO')}")

    print("\n✅ Todo listo para comenzar.\n")

if __name__ == "__main__":
    main()