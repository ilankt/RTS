import datetime
import time
from core.config import DEBUG_TO_FILE, DEBUG_FILE_PATH, DEBUG_ENABLED_CATEGORIES, DEBUG_FLUSH_INTERVAL
from utils.perf_stats import perf_stats

class DebugLogger:
    """Singleton debug logger that writes to file or console"""
    _instance = None
    _file_handle = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugLogger, cls).__new__(cls)
            if DEBUG_TO_FILE:
                try:
                    cls._instance._file_handle = open(DEBUG_FILE_PATH, 'w', buffering=1)
                    cls._instance._file_handle.write(f"=== Debug Log Started at {datetime.datetime.now()} ===\n")
                    cls._instance._last_flush = time.monotonic()
                except Exception as e:
                    print(f"Failed to open debug file: {e}")
                    cls._instance._file_handle = None
        return cls._instance
    
    def enabled(self, category="GENERAL"):
        """Cheap pre-check so hot paths can skip building f-strings for
        categories that are filtered out anyway."""
        return category in DEBUG_ENABLED_CATEGORIES

    def log(self, message, category="GENERAL"):
        """Log a debug message with timestamp and category"""
        if not self._should_log(message, category):
            return

        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] [{category}] {message}"
        
        if DEBUG_TO_FILE and self._file_handle:
            try:
                self._file_handle.write(formatted_message + "\n")
                perf_stats.increment("debug_log_writes")
                self._flush_if_needed()
            except:
                # Fallback to print if file write fails
                print(formatted_message)
        else:
            print(formatted_message)

    def _should_log(self, message, category):
        if category in DEBUG_ENABLED_CATEGORIES:
            return True
        text = str(message).upper()
        return "ERROR" in text or "WARNING" in text or "CRITICAL" in text

    def _flush_if_needed(self):
        now = time.monotonic()
        if now - getattr(self, "_last_flush", 0) >= DEBUG_FLUSH_INTERVAL:
            self._file_handle.flush()
            self._last_flush = now
    
    def close(self):
        """Close the debug file"""
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle.close()
            self._file_handle = None

# Global instance
debug_log = DebugLogger()
