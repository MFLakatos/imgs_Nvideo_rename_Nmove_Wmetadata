import os
import sys
import json
import shutil
import time
import subprocess
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from time import sleep

import requests
from PIL import Image
import pillow_heif
from dotenv import load_dotenv
from PIL.ExifTags import TAGS, GPSTAGS


class MediaOrganizer:
    def __init__(self,
                 input_dir: str,
                 output_dir: str,
                 ffmpeg_path: str,
                 ffprobe_path: str,
                 env_file: str = 'environmentVar.env') -> None:
        """
        Inicializa la clase con rutas a directorios, FFmpeg y archivo .env.
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        load_dotenv(env_file)
        self.opencage_key = os.getenv('OPENCAGE_API_KEY')
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
                print("API de OpenCage verificada correctamente.")
            else:
                print(f"Error en la API de OpenCage: {response_data.get('status', {}).get('message')}")
                raise Exception("Clave de API no válida o problema con la API.")
        except Exception as e:
            print(f"Error al verificar la API de OpenCage: {e}")
            raise        

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
            print(f"Error retrieving file times for {path}: {e}")
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
            print(f"Error extracting EXIF from {image_path}: {e}")
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
        usando metadatos temporales y geográficos.
        """
        no_metadata_path = os.path.join(self.output_dir, 'noMetadata')
        os.makedirs(os.path.join(no_metadata_path, 'videos'), exist_ok=True)
        os.makedirs(os.path.join(no_metadata_path, 'images'), exist_ok=True)

        for filename in os.listdir(self.input_dir):
            src_path = os.path.join(self.input_dir, filename)
            _, ext = os.path.splitext(filename.lower())

            if ext in ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.heic'):
                media_type = 'videos' if ext in ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif') else 'images'
                capture_time = None
                location_info = {'state': 'UnknownState', 'country': 'UnknownCountry'}

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
                            # print("Location info:", location_info)

                if not capture_time:
                    # Usa timestamps de sistema si no hay metadatos
                    ctime, mtime = self.get_file_times(src_path)
                    if ctime and mtime:
                        capture_time = datetime.fromtimestamp(min(ctime, mtime))

                if capture_time:
                    date_str = capture_time.strftime('%Y-%m-%d_%H-%M-%S')
                    # Incluir info de ubicación solo si es válida
                    if location_info["state"] != "UnknownState" and location_info["country"] != "UnknownCountry":
                        location_str = f"_{location_info['state']}_{location_info['country']}"
                    else:
                        location_str = ""
                    new_filename = f"{date_str}{location_str}{ext}"
                    dst_dir = os.path.join(self.output_dir, media_type)
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_path = os.path.join(dst_dir, new_filename)
                else:
                    # Caso sin metadata
                    dst_path = os.path.join(no_metadata_path, media_type, filename)

                shutil.copy2(src_path, dst_path)
                print(f"Copied: {src_path} → {dst_path}")

    def inspect_metadata(self, n: int = 5) -> None:
        """
        Imprime los metadatos de los primeros N archivos del directorio de entrada.
        Útil para identificar qué claves están disponibles, incluyendo GPS.
        """
        print(f"Inspeccionando metadatos de los primeros {n} archivos en {self.input_dir}...\n")
        count = 0
        for filename in sorted(os.listdir(self.input_dir)):
            if count >= n:
                break
            path = os.path.join(self.input_dir, filename)
            _, ext = os.path.splitext(filename.lower())

            print(f"\nArchivo {count + 1}: {filename}")
            print("-" * 60)
            if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.heic'):
                exif_data = self.get_exif_data(path)
                print("EXIF data:")
                for k, v in exif_data.items():
                    print(f"  {k}: {v}")
                gps_info = self.get_gps_info(exif_data)
                if gps_info:
                    print("\nGPSInfo (decodificada):")
                    for k, v in gps_info.items():
                        print(f"  {k}: {v}")

                    lat, lon = self.get_lat_lon(gps_info)
                    print(f"lat: {lat}, lon: {lon}")
                    if lat and lon:
                        location_info = self.reverse_geocode_opencage(lat, lon)
                        print("Location info:", location_info)
                else:
                    print("\nNo se encontró información GPS.")
            elif ext in ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif'):
                metadata = self.get_metadata_ffmpeg(path)
                print("Metadata FFmpeg (resumida):")
                if 'format' in metadata:
                    for k, v in metadata['format'].get('tags', {}).items():
                        print(f"  {k}: {v}")
                else:
                    print("  No se encontró sección 'format'.")
            else:
                print("Tipo de archivo no soportado para inspección.")
            count += 1

if __name__ == "__main__":
    print("Este archivo NO debería ejecutarse directamente.")
    print("Verificá que estés ejecutando ejecute_organizer.py y no media_organizer.py.")

