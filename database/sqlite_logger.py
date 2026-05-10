import sqlite3
import json
import time
import os
import logging
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log=logging.getLogger('SQLite')
 
DB_PATH= os.path.expanduser('~/industrial_gateway/gateway.db')
RETENTION_HOURS= 24    
CLEANUP_INTERVAL= 3600  
 
 
def init_database(conn):
    """Create all tables if they don't exist yet."""
    c = conn.cursor()
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL    NOT NULL,
            source    TEXT    NOT NULL,
            data_json TEXT    NOT NULL
        )
    ''')
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS fft_results (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      REAL NOT NULL,
            dominant_freq  REAL NOT NULL,
            latency_ms     REAL NOT NULL,
            amplitudes_json TEXT NOT NULL
        )
    ''')
 
    c.execute('''
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            rule      TEXT NOT NULL,
            severity  TEXT NOT NULL,
            reason    TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
    ''')
 
    c.execute('CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_readings(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_fft_ts    ON fft_results(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_anomaly_ts ON anomaly_events(timestamp)')
 
    conn.commit()
    log.info(f'Database initialised at {DB_PATH}')
 
 
def insert_item(conn, item):
    """
    Write one queue item to the appropriate table.
    Called for every item that comes out of the final queue stage.
    """
    src= item.get('source', '')
    ts= item.get('timestamp', time.time())
    c= conn.cursor()
 
    if src == 'fft':
        c.execute(
            'INSERT INTO fft_results (timestamp, dominant_freq, latency_ms, amplitudes_json) '
            'VALUES (?, ?, ?, ?)',
            (
                ts,
                item['dominant_freq'],
                item['latency_ms'],
                json.dumps(item['amplitudes']),
            )
        )
 
    elif src=='anomaly':
        c.execute(
            'INSERT INTO anomaly_events (timestamp, rule, severity, reason, data_json) '
            'VALUES (?, ?, ?, ?, ?)',
            (
                ts,
                item['rule'],
                item['severity'],
                item['reason'],
                json.dumps(item['data']),
            )
        )
 
    elif src in ('modbus','can','mpu6050'):
        slim = {k:v for k,v in item.items() if k!= 'accel_buffer'}
        c.execute(
            'INSERT INTO sensor_readings (timestamp, source, data_json) VALUES (?, ?, ?)',
            (ts, src, json.dumps(slim))
        )
    
 
 
def cleanup_old_data(conn):
    """Delete rows older than RETENTION_HOURS to keep DB size bounded."""
    cutoff = time.time() - (RETENTION_HOURS * 3600)
    c = conn.cursor()
    c.execute('DELETE FROM sensor_readings WHERE timestamp < ?', (cutoff,))
    c.execute('DELETE FROM fft_results     WHERE timestamp < ?', (cutoff,))
    c.execute('DELETE FROM anomaly_events  WHERE timestamp < ?', (cutoff,))
    conn.commit()
    log.info(f'Cleanup done. Removed data older than {RETENTION_HOURS}h')
 
 
def run_logger(queue, stop_event):
    """
    Main logger loop. Reads from queue and writes to SQLite.
    Runs as a thread inside main.py (not a separate Process).
 
    queue      -- the final output queue after anomaly detector
    stop_event -- set by main.py on shutdown
    """
    conn = sqlite3.connect(DB_PATH)
 
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')  
 
    init_database(conn)
 
    batch_size= 50      
    pending= 0
    total= 0
    last_cleanup= time.time()
 
    while not stop_event.is_set() or not queue.empty():
        try:
            item= queue.get(timeout=1.0)
            insert_item(conn, item)
            pending+= 1
            total+= 1
 
            # Commit in batches for performance.
            if pending >= batch_size:
                conn.commit()
                pending = 0
 
        except Exception as e:
            if 'Empty' not in str(type(e).__name__):
                log.error(f'Logger error: {e}')
 
        # Periodic cleanup
        if time.time() - last_cleanup > CLEANUP_INTERVAL:
            if pending > 0:
                conn.commit()
                pending = 0
            cleanup_old_data(conn)
            last_cleanup = time.time()
 
    if pending > 0:
        conn.commit()
 
    conn.close()
    log.info(f'Logger stopped. Total rows written: {total}')
