import os
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Application configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-for-document-analyzer'
    APP_NAME = 'Document Analyzer'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configuration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload size
    ALLOWED_EXTENSIONS = {'pdf', 'docx'}
    
    # Logging configuration
    LOG_FOLDER = os.path.join(BASE_DIR, 'logs')
    LOG_FILENAME = 'app.log'
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # Analysis configuration
    SIMILARITY_THRESHOLD = 0.8  # Default similarity threshold for paragraph comparison
    VARIABLE_PATTERNS = [
        r'<<([^>]+)>>',  # <<variable>>
        r'\{\{([^}]+)\}\}',  # {{variable}}
        r'\$\{([^}]+)\}',  # ${variable}
    ]

    @staticmethod
    def init_app(app):
        # Ensure upload directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Ensure log directory exists
        os.makedirs(app.config['LOG_FOLDER'], exist_ok=True)
        
        # Set up logging
        log_path = os.path.join(app.config['LOG_FOLDER'], app.config['LOG_FILENAME'])
        handler = RotatingFileHandler(
            log_path, 
            maxBytes=app.config['LOG_MAX_SIZE'],
            backupCount=app.config['LOG_BACKUP_COUNT']
        )
        handler.setFormatter(logging.Formatter(app.config['LOG_FORMAT']))
        handler.setLevel(app.config['LOG_LEVEL'])
        
        # Add handler to Flask logger
        app.logger.addHandler(handler)
        app.logger.setLevel(app.config['LOG_LEVEL'])
        
        # Add handler to SQLAlchemy logger
        logging.getLogger('sqlalchemy').addHandler(handler)
        logging.getLogger('sqlalchemy').setLevel(app.config['LOG_LEVEL'])
