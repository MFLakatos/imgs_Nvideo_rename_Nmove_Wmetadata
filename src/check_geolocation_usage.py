import logging
from datetime import datetime, timedelta

#TODO: adaptar a nueva estructura de carpetas
LOG_FILE_PATH = 'processed_files.txt'
MAX_USES_PER_24H = 2500

# Configurar logging
logger = logging.getLogger(__name__)
# logging.basicConfig(
#     level=logging.INFO,
#     format='[%(asctime)s] [%(levelname)s] %(message)s',
#     handlers=[
#         logging.FileHandler("check_geolocation_usage.log", encoding='utf-8'),
#         logging.StreamHandler()
#     ]
# )

def count_recent_geolocated_uses(log_file: str) -> int:
    now = datetime.now()
    twenty_four_hours_ago = now - timedelta(hours=24)
    count = 0

    try:
        with open(log_file, 'r') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) != 3:
                    logging.debug(f"Línea malformada ignorada: {line.strip()}")
                    continue

                _, geo_used, timestamp_str = parts

                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    logging.warning(f"Formato de fecha inválido: {timestamp_str}")
                    continue

                if geo_used == 'yes' and timestamp >= twenty_four_hours_ago:
                    count += 1

    except FileNotFoundError:
        logging.error(f"No se encontró el archivo de log: {log_file}")
        return 0

    return count

if __name__ == '__main__':
    logging.info("Iniciando chequeo de uso de geolocalización en las últimas 24 horas...")
    count = count_recent_geolocated_uses(LOG_FILE_PATH)
    logging.info(f"Cantidad de usos con geolocalización en las últimas 24 horas: {count} / {MAX_USES_PER_24H}")

    if count >= MAX_USES_PER_24H:
        logging.warning("⚠️  Se alcanzó o superó el límite diario de geolocalización. Se recomienda pausar el procesamiento.")
    else:
        logging.info("✅  Aún puedes continuar procesando archivos con geolocalización.")
