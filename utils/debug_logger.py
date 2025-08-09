import datetime
from core.config import DEBUG_TO_FILE, DEBUG_FILE_PATH

class DebugLogger:
    """Singleton debug logger that writes to file or console"""
    _instance = None
    _file_handle = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugLogger, cls).__new__(cls)
            if DEBUG_TO_FILE:
                try:
                    cls._instance._file_handle = open(DEBUG_FILE_PATH, 'w')
                    cls._instance._file_handle.write(f"=== Debug Log Started at {datetime.datetime.now()} ===\n")
                    cls._instance._file_handle.flush()
                except Exception as e:
                    print(f"Failed to open debug file: {e}")
                    cls._instance._file_handle = None
        return cls._instance
    
    def log(self, message, category="GENERAL"):
        """Log a debug message with timestamp and category"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] [{category}] {message}"
        
        if DEBUG_TO_FILE and self._file_handle:
            try:
                self._file_handle.write(formatted_message + "\n")
                self._file_handle.flush()
            except:
                # Fallback to print if file write fails
                print(formatted_message)
        else:
            print(formatted_message)
    
    def close(self):
        """Close the debug file"""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

# Global instance
debug_log = DebugLogger()