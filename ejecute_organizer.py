

import os
print()
# import media_organizer
# print("media_organizer file path:", media_organizer.__file__)

print("Working directory:", os.getcwd())    
print()
from media_organizer import MediaOrganizer


# source_folder = r'c:\Users\matias\Desktop\iCloudMFernandezLakatos\prueba_in'
source_folder = r'C:\Users\matias\Pictures\iCloud Photos\Photos'
# destination_folder = r'c:\Users\matias\Desktop\iCloudMFernandezLakatos\prueba_out'
destination_folder = r'D:\Respaldo_media\iPhone14v3'

organizer = MediaOrganizer(
    input_dir=source_folder,
    output_dir=destination_folder,
    ffmpeg_path=r"C:\Users\matias\ffmpeg\bin\ffmpeg.exe",
    ffprobe_path=r"C:\Users\matias\ffmpeg\bin\ffprobe.exe",
    env_file = 'environmentVar.env'
)

organizer.rename_and_copy_media()
organizer.inspect_metadata(3)  # Para ver los metadatos de los primeros 3 archivos




