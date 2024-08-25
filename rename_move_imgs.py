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

# Load environment variables from a .env file
load_dotenv('environmentVar.env')
# Retrieve the API key from an environment variable
OPENCAGE_API_KEY = os.getenv('OPENCAGE_API_KEY')

# Function to install a package using pip
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Function to import necessary packages
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

    try:
        import pillow_heif
    except ImportError:
        install_package('pillow-heif')
        import pillow_heif

import_packages()

# Full path to the ffmpeg executable
FFMPEG_PATH = r'C:\Users\matias\ffmpeg-2024-07-07-git-0619138639-full_build\bin\ffmpeg.exe'  # Replace with the actual path to ffmpeg.exe
FFPROBE_PATH = r'C:\Users\matias\ffmpeg-2024-07-07-git-0619138639-full_build\bin\ffprobe.exe'  # Replace with the actual path to ffprobe.exe

# Update the environment PATH
os.environ["PATH"] += os.pathsep + os.path.dirname(FFMPEG_PATH)

# Replace with your OpenCage API key: https://opencagedata.com/
OPENCAGE_API_KEY = 'c71cd83a1fff4bf29da27ea72fa94192'

# Function to get metadata using ffmpeg
def get_metadata_ffmpeg(path):
    try:
        result = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-show_format', '-show_streams', '-print_format', 'json', path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("FFmpeg not found. Please ensure ffmpeg is installed and in your PATH.")
        sys.exit(1)

# Function to reverse geocode using OpenCage API
def reverse_geocode(latitude, longitude):
    url = f'https://api.opencagedata.com/geocode/v1/json?q={latitude}+{longitude}&key={OPENCAGE_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['results']:
            components = data['results'][0]['components']
            department = components.get('state', 'UnknownDepartment')
            country = components.get('country', 'UnknownCountry')
            return department, country
    return 'UnknownDepartment', 'UnknownCountry'

# Function to get file creation and modification times
def get_file_times(path):
    try:
        creation_time = os.path.getctime(path)
        modification_time = os.path.getmtime(path)
        return creation_time, modification_time
    except Exception as e:
        print(f"Error retrieving file times: {str(e)}")
        return None, None

# Function to extract creation time from HEIC file
def get_creation_time_heic(file_path):
    try:
        image = Image.open(file_path)
        exif_data = image.info.get('exif', None)
        if exif_data:
            # Extract the creation time from EXIF metadata
            exif = pillow_heif.get_exif(file_path)
            creation_time = exif.get('DateTimeOriginal', 'N/A')
            return creation_time
    except Exception as e:
        print(f"Error retrieving HEIC creation time: {str(e)}")
    return 'N/A'

# Function to parse time in different formats
def parse_time(time_str):
    try:
        return time.strptime(time_str, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return time.strptime(time_str, "%a %b %d %H:%M:%S %Y")

# Function to rename and copy media files
def rename_and_copy_media(source_folder, destination_folder):
    no_metadata_folder = os.path.join(destination_folder, 'noMetadata')
    videos_no_metadata_folder = os.path.join(no_metadata_folder, 'videos')
    images_no_metadata_folder = os.path.join(no_metadata_folder, 'images')
    os.makedirs(videos_no_metadata_folder, exist_ok=True)
    os.makedirs(images_no_metadata_folder, exist_ok=True)

    print(f"Source folder: {source_folder}")
    print(f"Destination folder: {destination_folder}")

    for filename in os.listdir(source_folder):
        file_path = os.path.join(source_folder, filename)
        if filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.flv')):
            media_type = 'videos'
        elif filename.lower().endswith(('.jpg', '.jpeg', '.png', '.heic', '.bmp', '.gif', '.tiff')):
            media_type = 'images'
        else:
            continue

        metadata = get_metadata_ffmpeg(file_path) if media_type == 'videos' else None

        creation_time_ffmpeg = metadata['format']['tags'].get('creation_time', 'N/A') if metadata else 'N/A'
        location_ffmpeg = metadata['format']['tags'].get('location', 'N/A') if metadata else 'N/A'

        if filename.lower().endswith('.heic'):
            creation_time_heic = get_creation_time_heic(file_path)
            if creation_time_heic == 'N/A':
                creation_time, modification_time = get_file_times(file_path)
                if creation_time and modification_time:
                    older_time = min(creation_time, modification_time)
                else:
                    older_time = None
            else:
                older_time = time.mktime(parse_time(creation_time_heic))
        else:
            if creation_time_ffmpeg == 'N/A':
                creation_time, modification_time = get_file_times(file_path)
                if creation_time and modification_time:
                    older_time = min(creation_time, modification_time)
                else:
                    older_time = None
            else:
                older_time = time.mktime(parse_time(creation_time_ffmpeg))

        if older_time:
            older_datetime = datetime.fromtimestamp(older_time)
            year_folder = os.path.join(destination_folder, str(older_datetime.year))
            media_year_folder = os.path.join(year_folder, media_type)
            os.makedirs(media_year_folder, exist_ok=True)

            creation_time_str = older_datetime.strftime('%Y-%m-%d-%H-%M-%S')
            new_file_name = creation_time_str

            if location_ffmpeg != 'N/A':
                location_cleaned = location_ffmpeg.strip('/')
                latitude = float(location_cleaned[:8])
                longitude = float(location_cleaned[8:17])
                department, country = reverse_geocode(latitude, longitude)
                new_file_name += f"-{department}-{country}"

            new_file_name += os.path.splitext(filename)[1]
            new_file_path = os.path.join(media_year_folder, new_file_name)
        else:
            new_file_name = filename
            new_file_path = os.path.join(no_metadata_folder if media_type == 'images' else videos_no_metadata_folder, new_file_name)

        shutil.copy2(file_path, new_file_path)
        print(f'Copied and renamed: {filename} -> {new_file_name}')

# Main function
def main():
    source_folder = r'C:\Users\matias\Desktop\iCloudMFernandezLakatos\heic'  # Replace with your source folder
    destination_folder = r'D:\Respaldo_media\pruebaPyImages'  # Replace with your destination folder

    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)

    rename_and_copy_media(source_folder, destination_folder)

if __name__ == '__main__':
    main()
