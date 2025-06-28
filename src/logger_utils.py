import logging
import sys

def setup_logging_from_config(config: dict):
    """
    Configura el sistema de logging según los parámetros del diccionario de configuración.
    
    - Si logging está deshabilitado, se suprimen todos los mensajes.
    - Si está habilitado, crea dos handlers:
        - Uno para archivo (nivel DEBUG)
        - Uno para consola (nivel especificado)
    """
    logging_cfg = config.get('logging', {})

    if not logging_cfg.get('enabled', False):
        logging.disable(logging.CRITICAL)
        return

    log_file = logging_cfg.get('log_file', 'media_organizer.log')
    log_level_str = logging_cfg.get('log_level', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Captura todo

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Handler para archivo (todo)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

    # Handler para consola (nivel especificado)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
