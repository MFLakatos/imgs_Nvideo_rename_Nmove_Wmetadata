import os
import sys
import json
import shutil
from datetime import datetime, timedelta
import subprocess
from typing import Optional, Tuple, Dict, Any
from time import sleep
import hashlib

import requests
from PIL import Image
import pillow_heif
from dotenv import load_dotenv
from PIL.ExifTags import TAGS, GPSTAGS

from src.logger_utils import setup_logging_from_config
import logging

logger = logging.getLogger(__name__)

class MediaOrganizer:
    def __init__(self, config: dict) -> None:
        self.input_dir = config['input_dir']
        self.output_dir = config['output_dir']
        self.ffmpeg_path = config['ffmpeg_path']
        self.ffprobe_path = config['ffprobe_path']
        self.processed_log_path = config['log_file']
        self.max_files_per_session = config['max_files_per_session']
        self.env_file = config.get('env_file', 'environmentVar.env')
        self.delete_after = config.get('delete_after_processing', False)
        self.skip_already_processed = config.get('skip_already_processed', True)

        setup_logging_from_config(config)

        self.supported_video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif'}
        self.supported_image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.heic'}

        self._ensure_log_file_exists()
        self.processed_files = self._load_processed_files()
        logging.debug(f"🔄 Archivos procesados cargados: {len(self.processed_files)}")

        load_dotenv(self.env_file)
        self.opencage_key = os.getenv('OPENCAGE_API_KEY')
        if not self.opencage_key:
            raise ValueError("Falta OPENCAGE_API_KEY")
        self.nominatim_email = os.getenv('my_email')

        # Verificar si la API de OpenCage funciona con una solicitud de prueba
        self._check_opencage_api()

        # Agrega FFmpeg al PATH del sistema
        os.environ["PATH"] += os.pathsep + os.path.dirname(self.ffmpeg_path)

        self._import_optional_packages()

    def _check_opencage_api(self) -> None:
        """
        Verifica si la API de OpenCage funciona correctamente.
        Si no es así, muestra un mensaje y detiene la ejecución.
        """
        test_url = f'https://api.opencagedata.com/geocode/v1/json?q=-34.91322777777778+-56.15398333333333&key={self.opencage_key}'
        try:
            response = requests.get(test_url)
            response_data = response.json()
            if response.status_code == 200 and response_data.get('status', {}).get('code') == 200:
                logging.debug("API de OpenCage verificada correctamente.")
            else:
                logging.error(f"Error en la API de OpenCage: {response_data.get('status', {}).get('message')}")
                raise Exception("Clave de API no válida o problema con la API.")
        except Exception as e:
            logging.error(f"Error al verificar la API de OpenCage: {e}")
            raise        

    def _ensure_log_file_exists(self) -> None:
        """Crea el archivo de log si no existe."""
        if not os.path.exists(self.processed_log_path):
            with open(self.processed_log_path, 'w', encoding='utf-8') as f:
                pass

    # def _load_processed_files(self) -> Dict[str, Dict[str, str]]:
    #     """
    #     Carga un diccionario con información de archivos procesados:
    #     filename -> {'geo': 'yes'/'no', 'timestamp': 'ISO format'}
    #     """
    #     processed = {}
    #     with open(self.processed_log_path, 'r') as f:
    #         for line in f:
    #             try:
    #                 name, geo, timestamp = line.strip().split('|')
    #                 processed[name] = {'geo': geo, 'timestamp': timestamp}
    #             except ValueError:
    #                 continue
    #     return processed
    def _load_processed_files(self) -> Dict[str, Dict[str, str]]:
        processed = {}
        if not os.path.exists(self.processed_log_path):
            return processed

        with open(self.processed_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    file_hash, original, final, geo, timestamp = line.strip().split('|')
                    processed[file_hash] = {
                        'original': original,
                        'final': final,
                        'geo': geo,
                        'timestamp': timestamp
                    }
                except ValueError:
                    continue
        return processed

    # def _mark_as_processed(self, filename: str, used_geolocation: bool) -> None:
    #     """Agrega un archivo al registro de procesados."""
    #     geo_status = 'yes' if used_geolocation else 'no'
    #     timestamp = datetime.now().isoformat()
    #     with open(self.processed_log_path, 'a') as f:
    #         f.write(f"{filename}|{geo_status}|{timestamp}\n")
    #     self.processed_files[filename] = {'geo': geo_status, 'timestamp': timestamp}
    def _mark_as_processed(self, original_filename: str, final_filename: str, used_geolocation: bool, file_hash: str) -> None:
        geo_status = 'yes' if used_geolocation else 'no'
        timestamp = datetime.now().isoformat()
        line = f"{file_hash}|{original_filename}|{final_filename}|{geo_status}|{timestamp}\n"
        with open(self.processed_log_path, 'a', encoding='utf-8') as f:
            f.write(line)
        self.processed_files[file_hash] = {
            'original': original_filename,
            'final': final_filename,
            'geo': geo_status,
            'timestamp': timestamp
        }

    def _count_geolocations_last_24h(self) -> int:
        """
        Cuenta cuántos archivos fueron geolocalizados ('yes') en las últimas 24 horas.
        """
        now = datetime.now()
        limit_time = now - timedelta(hours=24)
        count = 0

        try:
            with open(self.processed_log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) != 3:
                        continue
                    _, geo_status, timestamp_str = parts
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        if geo_status == 'yes' and timestamp >= limit_time:
                            count += 1
                    except ValueError:
                        continue
        except FileNotFoundError:
            logging.warning(f"No se encontró el archivo de log: {self.processed_log_path}")
        return count

    # def check_already_processed_in_input(self):
    #     # Listar archivos en input_dir con extensiones soportadas
    #     all_files = [f for f in os.listdir(self.input_dir)
    #                 if os.path.splitext(f.lower())[1] in self.supported_image_exts.union(self.supported_video_exts)]

    #     if not all_files:
    #         logging.error(f"No hay archivos en el directorio de origen {self.input_dir}.")
    #         return


    #     logging.debug(f"🧾 Archivos registrados como procesados en el log: {list(self.processed_files.keys())}")
    #     logging.debug(f"📁 Archivos presentes en el input: {all_files}")

    #     # Filtrar los que ya están procesados (según self.processed_files)
    #     processed_in_input = [f for f in all_files if f in self.processed_files]
    #     not_processed_in_input = [f for f in all_files if f not in self.processed_files]

    #     logging.info(f"\n🗂️  Análisis del directorio de entrada: {self.input_dir}")
    #     logging.info(f"📄 Total de archivos multimedia encontrados: {len(all_files)}")
    #     logging.info(f"✅ Archivos ya registrados como procesados (según nombre): {len(processed_in_input)}")
    #     logging.info(f"🆕 Archivos nuevos (no encontrados en el log): {len(not_processed_in_input)}")

    #     if processed_in_input:
    #         logging.debug("📝 Lista de archivos ya procesados:")
    #         for f in processed_in_input:
    #             logging.debug(f"  - {f}")
    #     if not_processed_in_input:
    #         logging.debug("📥 Lista de archivos nuevos (a procesar):")
    #         for f in not_processed_in_input:
    #             logging.debug(f"  - {f}")
    def check_already_processed_in_input(self):
        all_files = [
            f for f in os.listdir(self.input_dir)
            if os.path.splitext(f.lower())[1] in self.supported_image_exts.union(self.supported_video_exts)
        ]
        
        processed_hashes = set(self.processed_files.keys())
        processed_in_input = []
        not_processed_in_input = []

        for filename in all_files:
            path = os.path.join(self.input_dir, filename)
            file_hash = self.compute_file_hash(path)
            if file_hash in processed_hashes:
                processed_in_input.append(filename)
            else:
                not_processed_in_input.append(filename)

        logging.info(f"\n🗂️  Análisis del directorio de entrada: {self.input_dir}")
        logging.info(f"📄 Total de archivos multimedia encontrados: {len(all_files)}")
        logging.info(f"✅ Archivos ya registrados como procesados (según hash): {len(processed_in_input)}")
        logging.info(f"🆕 Archivos nuevos (no encontrados en el log): {len(not_processed_in_input)}")

    def compute_file_hash(self, path: str, block_size=65536) -> str:
        
        hasher = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(block_size), b''):
                hasher.update(chunk)
        return hasher.hexdigest()


    def _install_package(self, package: str) -> None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

    def _import_optional_packages(self) -> None:
        global ffmpeg, TinyTag
        try:
            import ffmpeg
        except ImportError:
            self._install_package('ffmpeg-python')
            import ffmpeg

        try:
            from tinytag import TinyTag
        except ImportError:
            self._install_package('tinytag')
            from tinytag import TinyTag

    def get_metadata_ffmpeg(self, path: str) -> Dict[str, Any]:
        """
        Extrae metadatos de archivos multimedia usando ffprobe (FFmpeg).
        """
        result = subprocess.run(
            [self.ffprobe_path, '-v', 'error', '-show_format', '-show_streams', '-print_format', 'json', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return json.loads(result.stdout)

    # def reverse_geocode_opencage(self, lat: float, lon: float) -> Tuple[str, str]:
    #     """
    #     Obtiene ubicación (departamento y país) a partir de coordenadas usando OpenCage API.
    #     """
    #     url = f'https://api.opencagedata.com/geocode/v1/json?q={lat}+{lon}&key={self.opencage_key}'
    #     response = requests.get(url)
    #     if response.status_code == 200:
    #         results = response.json().get('results')
    #         if results:
    #             components = results[0].get('components', {})
    #             return components.get('state', 'UnknownState'), components.get('country', 'UnknownCountry')
    #     return 'UnknownState', 'UnknownCountry'

    def reverse_geocode_opencage(self, lat: float, lon: float) -> Dict[str, str]:
        """
        Obtiene ubicación (departamento y país) a partir de coordenadas usando OpenCage API.
        """
        url = f'https://api.opencagedata.com/geocode/v1/json?q={lat}+{lon}&key={self.opencage_key}'
        response = requests.get(url)
        if response.status_code == 200:
            results = response.json().get('results')
            if results:
                components = results[0].get('components', {})
                return {
                    'state': components.get('state', 'UnknownState'),
                    'country': components.get('country', 'UnknownCountry')
                }
        
        return {'state': 'UnknownState', 'country': 'UnknownCountry'}

    def get_file_times(self, path: str) -> Tuple[Optional[float], Optional[float]]:
        try:
            return os.path.getctime(path), os.path.getmtime(path)
        except Exception as e:
            logging.error(f"Error retrieving file times for {path}: {e}")
            return None, None

    def get_exif_data(self, image_path: str) -> Dict[str, Any]:
        """
        Extrae metadatos EXIF de imágenes (incluyendo HEIC).
        """
        try:
            if image_path.lower().endswith('.heic'):
                heif_file = pillow_heif.read_heif(image_path)
                exif_data = heif_file.metadata.get('Exif', {})
                return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
            else:
                with Image.open(image_path) as img:
                    exif_data = img._getexif()
                    if exif_data:
                        return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
            return {}
        except Exception as e:
            logging.error(f"Error extracting EXIF from {image_path}: {e}")
            return {}

    def get_gps_info(self, exif_data: Dict[str, Any]) -> Dict[str, Any]:
        gps_info = exif_data.get('GPSInfo')
        if not gps_info:
            return {}
        return {GPSTAGS.get(tag, tag): value for tag, value in gps_info.items()}

    def convert_to_degrees(self, value: Tuple[float, float, float]) -> float:
        d, m, s = value
        return d + (m / 60.0) + (s / 3600.0)

    def get_lat_lon(self, gps_info: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
        try:
            lat = self.convert_to_degrees(gps_info['GPSLatitude'])
            if gps_info['GPSLatitudeRef'] != 'N':
                lat = -lat
            lon = self.convert_to_degrees(gps_info['GPSLongitude'])
            if gps_info['GPSLongitudeRef'] != 'E':
                lon = -lon
            return lat, lon
        except Exception:
            return None, None

    def get_capture_time_exif(self, exif_data: Dict[str, Any]) -> Optional[datetime]:
        time_str = exif_data.get('DateTimeOriginal')
        if time_str:
            try:
                return datetime.strptime(time_str, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                return None
        return None

    def get_capture_time_ffmpeg(self, metadata: Dict[str, Any]) -> Optional[datetime]:
        capture_time = metadata['format'].get('tags', {}).get('creation_time')
        if capture_time:
            try:
                return datetime.fromisoformat(capture_time.replace('Z', '+00:00'))
            except ValueError:
                return None
        return None

    def rename_and_copy_media(self) -> None:
        """
        Renombra y copia archivos multimedia desde el directorio de entrada al de salida,
        usando metadatos temporales y geográficos. Guarda en el log si se usó geolocalización.
        """
        geo_uses_last_24h = self._count_geolocations_last_24h()
        if geo_uses_last_24h >= self.max_files_per_session:
            logging.warning(f"Se alcanzó el límite diario de {self.max_files_per_session} geolocalizaciones. Abortando procesamiento.")
            return
        else:
            logging.info(f"Geolocalizaciones en las últimas 24 horas: {geo_uses_last_24h} / {self.max_files_per_session}")

        no_metadata_path = os.path.join(self.output_dir, 'noMetadata')
        os.makedirs(os.path.join(no_metadata_path, 'videos'), exist_ok=True)
        os.makedirs(os.path.join(no_metadata_path, 'images'), exist_ok=True)

        processed_count = 0

        for filename in os.listdir(self.input_dir):
            if self.skip_already_processed and filename in self.processed_files:
                continue  # omitimos archivos ya procesados según el log

            if processed_count >= self.max_files_per_session:
                logging.warning(f"Límite de {self.max_files_per_session} archivos alcanzado. Deteniendo.")
                break

            src_path = os.path.join(self.input_dir, filename)
            _, ext = os.path.splitext(filename.lower())

            if ext in self.supported_video_exts | self.supported_image_exts:
                media_type = 'videos' if ext in self.supported_video_exts else 'images'
                capture_time = None
                location_info = {'state': 'UnknownState', 'country': 'UnknownCountry'}
                used_geolocation = False

                try:
                    if media_type == 'videos':
                        metadata = self.get_metadata_ffmpeg(src_path)
                        capture_time = self.get_capture_time_ffmpeg(metadata)
                    else:
                        exif = self.get_exif_data(src_path)
                        capture_time = self.get_capture_time_exif(exif)
                        gps_info = self.get_gps_info(exif)
                        if gps_info:
                            lat, lon = self.get_lat_lon(gps_info)
                            if lat and lon:
                                location_info = self.reverse_geocode_opencage(lat, lon)
                                used_geolocation = True

                    if not capture_time:
                        ctime, mtime = self.get_file_times(src_path)
                        if ctime and mtime:
                            capture_time = datetime.fromtimestamp(min(ctime, mtime))
                            logging.warning(f"No capture time en metadatos para {filename}, usando timestamps de sistema.")

                    if capture_time:
                        date_str = capture_time.strftime('%Y-%m-%d_%H-%M-%S')
                        if location_info["state"] != "UnknownState" and location_info["country"] != "UnknownCountry":
                            location_str = f"_{location_info['state']}_{location_info['country']}"
                        else:
                            location_str = ""
                        new_filename = f"{date_str}{location_str}{ext}"
                        dst_dir = os.path.join(self.output_dir, media_type)
                        os.makedirs(dst_dir, exist_ok=True)
                        dst_path = os.path.join(dst_dir, new_filename)
                    else:
                        dst_path = os.path.join(no_metadata_path, media_type, filename)
                    if os.path.exists(dst_path):
                        logging.info(f"Ya existe en destino, no se copia: {dst_path}")
                    else:
                        shutil.copy2(src_path, dst_path)
                        logging.info(f"Copied: {src_path} → {dst_path}")
                    file_hash = self.compute_file_hash(src_path)
                    self._mark_as_processed(filename, os.path.basename(dst_path), used_geolocation, file_hash)
                    # self._mark_as_processed(filename, used_geolocation)
                    processed_count += 1

                except Exception as e:
                    logging.error(f"Error procesando {filename}: {e}")
            if self.delete_after:
                self._delete_processed_files()

    def _delete_processed_files(self):
        files_to_delete, unprocessed = self._get_files_to_delete()

        if unprocessed:
            print("⚠️ Archivos no procesados presentes, no se eliminarán:")
            for f in unprocessed:
                print(" -", f)

        if not files_to_delete:
            print("✅ No hay archivos para eliminar.")
            return

        confirm = input("\n¿Eliminar archivos procesados del directorio de origen? (s/n): ").lower()
        if confirm != 's':
            print("❌ Cancelado.")
            return

        for path in files_to_delete:
            try:
                os.remove(path)
                print(f"🗑️ Eliminado: {os.path.basename(path)}")
            except Exception as e:
                print(f"⚠️ Error al eliminar {path}: {e}")

    def _get_files_to_delete(self):
        files_to_delete = []
        unprocessed = []
        for file in os.listdir(self.input_dir):
            file_path = os.path.join(self.input_dir, file)
            if os.path.isfile(file_path):
                if file in self.processed_files:
                    files_to_delete.append(file_path)
                else:
                    unprocessed.append(file)
        return files_to_delete, unprocessed



    def inspect_metadata(self, n: int = 5) -> None:
        """
        Imprime los metadatos de los primeros N archivos del directorio de entrada.
        Útil para identificar qué claves están disponibles, incluyendo GPS.
        """
        logging.info(f"Inspeccionando metadatos de los primeros {n} archivos en {self.input_dir}...\n")
        count = 0
        for filename in sorted(os.listdir(self.input_dir)):
            if count >= n:
                break
            path = os.path.join(self.input_dir, filename)
            _, ext = os.path.splitext(filename.lower())

            logging.info(f"\nArchivo {count + 1}: {filename}")
            logging.info("-" * 60)
            if ext in self.supported_image_exts:
                exif_data = self.get_exif_data(path)
                logging.info("EXIF data:")
                for k, v in exif_data.items():
                    logging.info(f"  {k}: {v}")
                gps_info = self.get_gps_info(exif_data)
                if gps_info:
                    logging.info("\nGPSInfo (decodificada):")
                    for k, v in gps_info.items():
                        logging.info(f"  {k}: {v}")

                    lat, lon = self.get_lat_lon(gps_info)
                    logging.info(f"lat: {lat}, lon: {lon}")
                    if lat and lon:
                        location_info = self.reverse_geocode_opencage(lat, lon)
                        logging.info(f"Location info: {location_info}")

                else:
                    logging.info("\nNo se encontró información GPS.")
            elif ext in self.supported_video_exts:
                metadata = self.get_metadata_ffmpeg(path)
                logging.info("Metadata FFmpeg (resumida):")
                if 'format' in metadata:
                    for k, v in metadata['format'].get('tags', {}).items():
                        logging.info(f"  {k}: {v}")
                else:
                    logging.info("No se encontró sección 'format'.")
            else:
                logging.info("Tipo de archivo no soportado para inspección.")
            count += 1

if __name__ == "__main__":
    logging.warning("Este archivo NO debería ejecutarse directamente.")
    logging.warning("Verificá que estés ejecutando ejecute_organizer.py y no media_organizer.py.")
