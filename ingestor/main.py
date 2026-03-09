"""
Ingestor main entry point
"""

import threading

from ingestor import app, start_watchers, _flush_loop, INGESTOR_PORT, logger

if __name__ == '__main__':
    logger.info(f"Starting MAYASEC Ingestor on port {INGESTOR_PORT}")
    flush_thread = threading.Thread(target=_flush_loop, daemon=True)
    flush_thread.start()
    start_watchers(ingest_func=app.config['INGEST_FUNC'])
    app.run(host='0.0.0.0', port=INGESTOR_PORT, debug=False)
