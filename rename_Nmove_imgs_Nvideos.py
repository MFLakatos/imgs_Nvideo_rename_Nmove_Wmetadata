import os
import subprocess
import sys
import time
import json
import shutil
import requests
from datetime import datetime
from PIL import Image
import pillow_heif
from dotenv import load_dotenv
from PIL.ExifTags import TAGS, GPSTAGS
from time import sleep

# Load environment variables from a .env file
load_dotenv('environmentVar.env')

# Retrieve the API key from an environment variable
OPENCAGE_API_KEY = os.getenv('OPENCAGE_API_KEY')


def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def import_packages():
    global ffmpeg
    try:
        import ffmpeg
    except ImportError:
        install_package('ffmpeg-python')
        import ffmpeg

    try:
        from tinytag import TinyTag
    except ImportError:
        install_package('tinytag')
        from tinytag import TinyTag


import_packages()

# Full path to the ffmpeg executable
FFMPEG_PATH = r'C:\Users\matias\ffmpeg-2024-07-07-git-0619138639-full_build\bin\ffmpeg.exe'
FFPROBE_PATH = r'C:\Users\matias\ffmpeg-2024-07-07-git-0619138639-full_build\bin\ffprobe.exe'

os.environ["PATH"] += os.pathsep + os.path.dirname(FFMPEG_PATH)


def get_metadata_ffmpeg(path):
    try:
        result = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-show_format', '-show_streams', '-print_format', 'json', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("FFmpeg not found. Please ensure ffmpeg is installed and in your PATH.")
        sys.exit(1)


def reverse_geocode(latitude, longitude):
    url = f'https://api.opencagedata.com/geocode/v1/json?q={latitude}+{longitude}&key={OPENCAGE_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['results']:
            components = data['results'][0]['components']
            department = components.get('state', 'UnknownState')
            country = components.get('country', 'UnknownCountry')
            return department, country
    return 'UnknownState', 'UnknownCountry'


def get_file_times(path):
    try:
        creation_time = os.path.getctime(path)
        modification_time = os.path.getmtime(path)
        return creation_time, modification_time
    except Exception as e:
        print(f"Error retrieving file times: {str(e)}")
        return None, None


def parse_time(time_str):
    if not time_str:
        return None
    try:
        return time.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        try:
            return time.strptime(time_str, "%a %b %d %H:%M:%S %Y")
        except ValueError:
            print(f"Unrecognized time format: {time_str}")
            return None


def get_lat_lon_from_ffmpeg_location(location_ffmpeg):
    location_cleaned = location_ffmpeg.strip('/')
    latitude = float(location_cleaned[:8])
    longitude = float(location_cleaned[8:17])
    return latitude, longitude


def get_capture_time_ffmpeg(metadata):
    capture_time = metadata['format'].get('tags', {}).get('creation_time')
    if capture_time:
        try:
            return datetime.fromisoformat(capture_time.replace('Z', '+00:00'))
        except ValueError:
            pass
    return None


def get_capture_time_exif(exif_data):
    """Extract capture time from EXIF data."""
    capture_time = exif_data.get('DateTimeOriginal')
    if capture_time:
        try:
            return datetime.strptime(capture_time, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            pass
    return None


def get_exif_data(image_path):
    """Extract EXIF data from an image."""
    try:
        if image_path.lower().endswith('.heic'):
            heif_file = pillow_heif.read_heif(image_path)
            exif_data = heif_file.metadata.get('Exif', {})
            return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
        else:
            with Image.open(image_path) as img:
                exif_data = img._getexif()
                if exif_data is not None:
                    return {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
                return {}
    except AttributeError:
        print(f"AttributeError: _getexif not found for image {image_path}")
        return {}
    except Exception as e:
        print(f"Error extracting EXIF data from image {image_path}: {e}")
        return {}


def get_gps_info(exif_data):
    """Extract GPS information from EXIF data."""
    gps_info = exif_data.get('GPSInfo')
    if gps_info:
        gps_data = {}
        for tag, value in gps_info.items():
            decoded = GPSTAGS.get(tag, tag)
            gps_data[decoded] = value
        return gps_data
    return {}


def convert_to_degrees(value):
    """Convert GPS coordinates to degrees."""
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)


def get_lat_lon(gps_info):
    """Get latitude and longitude from GPS info."""
    lat = lon = None
    gps_latitude = gps_info.get('GPSLatitude')
    gps_latitude_ref = gps_info.get('GPSLatitudeRef')
    gps_longitude = gps_info.get('GPSLongitude')
    gps_longitude_ref = gps_info.get('GPSLongitudeRef')

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = convert_to_degrees(gps_latitude)
        if gps_latitude_ref != 'N':
            lat = -lat
        lon = convert_to_degrees(gps_longitude)
        if gps_longitude_ref != 'E':
            lon = -lon
    return lat, lon


def get_location(lat, lon):
    """Reverse geocode latitude and longitude to get location information using Nominatim."""
    email = os.getenv('my_email')
    retries = 3
    delay_seconds = 1  # Base delay in seconds
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    for attempt in range(retries):
        try:
            response = requests.get(
                f"https://nominatim.openstreetmap.org/search?q={lat}%2C+{lon}&format=jsonv2&addressdetails=1&limit=1&email={email}",
                headers=headers)
            response.raise_for_status()
            data = response.json()
            if data:
                location = data[0]
                address = location.get('address', {})
                state = address.get('state', 'UnknownState')
                country = address.get('country', 'UnknownCountry')
                return {'state': state, 'country': country}
            else:
                return {'state': 'UnknownState', 'country': 'UnknownCountry'}
        except requests.exceptions.HTTPError as err:
            if response.status_code == 403:
                print(
                    f"Geocoding service error (attempt {attempt + 1}/{retries}): {response.status_code} - Forbidden. Waiting before retrying...")
                sleep(delay_seconds)
                delay_seconds *= 2  # Exponential backoff
            else:
                print(f"Geocoding service error (attempt {attempt + 1}/{retries}): {err}")
        except Exception as e:
            print(f"Geocoding service error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:  # Retry if not the last attempt
                print(f"Retrying in {delay_seconds} second(s).")
                sleep(delay_seconds)
                delay_seconds *= 2  # Exponential backoff

    return {'state': 'UnknownState', 'country': 'UnknownCountry'}


def rename_and_copy_media(source_folder, destination_folder):
    no_metadata_folder = os.path.join(destination_folder, 'noMetadata')
    videos_no_metadata_folder = os.path.join(no_metadata_folder, 'videos')
    images_no_metadata_folder = os.path.join(no_metadata_folder, 'images')
    os.makedirs(videos_no_metadata_folder, exist_ok=True)
    os.makedirs(images_no_metadata_folder, exist_ok=True)


    for filename in os.listdir(source_folder):
        exif_data = None
        gps_info = None
        capture_time = None
        creation_time_ffmpeg = None
        metadata = {}  # Initialize metadata

        file_path = os.path.join(source_folder, filename)
        file_base, file_ext = os.path.splitext(filename)

        if filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif','.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.heic')):
            if filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.flv', '.gif')):
                media_type = 'videos'
                metadata = get_metadata_ffmpeg(file_path)
                capture_time = get_capture_time_ffmpeg(metadata)
                creation_time_ffmpeg = metadata['format'].get('tags', {}).get('creation_time', 'N/A')
            elif filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
                media_type = 'images'
                exif_data = get_exif_data(file_path)
                gps_info = get_gps_info(exif_data)
                capture_time = get_capture_time_exif(exif_data)
                creation_time_ffmpeg = 'N/A'
                # print(capture_time)
            elif filename.lower().endswith(('.heic')):
                media_type = 'images'
                metadata = get_metadata_ffmpeg(file_path)
                capture_time = get_capture_time_ffmpeg(metadata)

            if capture_time:
                older_datetime = capture_time
            elif media_type == 'images':
                creation_time, modification_time = get_file_times(file_path)
                older_time = min(creation_time, modification_time) if creation_time and modification_time else None
                if older_time:
                    older_datetime = datetime.fromtimestamp(older_time)
                else:
                    older_datetime = None
            elif creation_time_ffmpeg == 'N/A' and media_type == 'videos':
                creation_time, modification_time = get_file_times(file_path)
                older_time = min(creation_time, modification_time) if creation_time and modification_time else None
                if older_time:
                    older_datetime = datetime.fromtimestamp(older_time)
                else:
                    older_datetime = None
            else:
                parsed_time = parse_time(creation_time_ffmpeg)
                print(parse_time)
                if parsed_time:
                    older_time = time.mktime(parsed_time)
                    older_datetime = datetime.fromtimestamp(older_time)
                else:
                    older_datetime = None

            if older_datetime:
                new_file_name = older_datetime.strftime('%Y-%m-%d-%H-%M-%S')

                if 'location' in metadata.get('format', {}).get('tags', {}):
                    location_ffmpeg = metadata['format']['tags']['location']
                    latitude, longitude = get_lat_lon_from_ffmpeg_location(location_ffmpeg)
                    department, country = reverse_geocode(latitude, longitude)
                    new_file_name += f"-{department}-{country}"
                elif gps_info:
                    lat, lon = get_lat_lon(gps_info)
                    location = get_location(lat, lon)
                    state = location.get('state', 'UnknownState')
                    country = location.get('country', 'UnknownCountry')
                    new_file_name += f'-{state}-{country}'

                new_file_name += file_ext  # Append the original file extension
                media_year_folder = os.path.join(destination_folder, str(older_datetime.year), media_type)
                os.makedirs(media_year_folder, exist_ok=True)
                new_file_path = os.path.join(media_year_folder, new_file_name)
            else:
                new_file_name = filename
                new_file_path = os.path.join(
                    images_no_metadata_folder if media_type == 'images' else videos_no_metadata_folder, new_file_name)

            # Ensure the destination folder exists
            dest_folder = os.path.dirname(new_file_path)
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)

            shutil.copy2(file_path, new_file_path)
            print(f'Copied and renamed: {new_file_name} <- {filename}')
        else:
            # For other formats, keep the original filename
            new_file_path = os.path.join(no_metadata_folder, filename)
            shutil.copy2(file_path, new_file_path)
            print(f'Copied: {filename} -> {filename}')


def main():
    source_folder = r'C:\Users\matias\Desktop\iCloudMFernandezLakatos\all_formats'
    destination_folder = r'C:\Users\matias\Desktop\iCloudMFernandezLakatos\all_formats_destination'

    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    rename_and_copy_media(source_folder, destination_folder)


if __name__ == '__main__':
    main()


    ### imgs:
        # else:
        #     print(media_type)
        #
        #     file_path = os.path.join(source_folder, filename)
        #     exif_data = get_exif_data(file_path)
        #     print(exif_data)
        #     date_time = get_date_time_original(exif_data)
        #     gps_info = get_gps_info(exif_data)
        #
        #     # print(f"Processing file: {file_path}")
        #     if date_time:
        #         year_folder = os.path.join(destination_folder, str(date_time.year))
        #         os.makedirs(year_folder, exist_ok=True)
        #
        #         if gps_info:
        #             lat, lon = get_lat_lon(gps_info)
        #             location = get_location(lat, lon)
        #             state = location.get('state', '')
        #             country = location.get('country', '')
        #             if state and country:
        #                 new_filename = date_time.strftime(
        #                     '%Y-%m-%d-%H-%M-%S') + f'-{state}-{country}{os.path.splitext(filename)[1]}'
        #             else:
        #                 new_filename = date_time.strftime('%Y-%m-%d-%H-%M-%S') + f'{os.path.splitext(filename)[1]}'
        #         else:
        #             new_filename = date_time.strftime('%Y-%m-%d-%H-%M-%S') + f'{os.path.splitext(filename)[1]}'
        #
        #         new_file_path = os.path.join(year_folder, new_filename)
        #     else:
        #         new_filename = filename
        #         new_file_path = os.path.join(no_metadata_folder, new_filename)
        #
        #     shutil.copy2(file_path, new_file_path)
        #     print(f'Copied and renamed: {filename} -> {new_filename}')

