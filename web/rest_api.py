import json
import os
import time
import sqlite3
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import psutil

DB_PATH    = os.path.expanduser('~/industrial_gateway/gateway.db')
START_TIME = time.time()

router = APIRouter()


@router.get('/api/status')
async def get_status():
    cpu_per_core = psutil.cpu_percent(percpu=True)
    mem          = psutil.virtual_memory()
    uptime_sec   = int(time.time() - START_TIME)
    return JSONResponse({
        'uptime_seconds':  uptime_sec,
        'uptime_human':    datetime.utcfromtimestamp(uptime_sec).strftime('%H:%M:%S'),
        'cpu_per_core':    cpu_per_core,
        'cpu_total':       sum(cpu_per_core) / len(cpu_per_core),
        'memory_used_mb':  round(mem.used / 1024 / 1024),
        'memory_total_mb': round(mem.total / 1024 / 1024),
        'memory_pct':      mem.percent,
    })


@router.get('/api/history')
async def get_history(minutes: int = 5):
    minutes = min(minutes, 60)
    cutoff  = time.time() - (minutes * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    modbus_rows = conn.execute(
        'SELECT timestamp, data_json FROM sensor_readings '
        'WHERE source = ? AND timestamp > ? ORDER BY timestamp ASC '
        'LIMIT 1000',
        ('modbus', cutoff)
    ).fetchall()

    can_rows = conn.execute(
        'SELECT timestamp, data_json FROM sensor_readings '
        'WHERE source = ? AND timestamp > ? ORDER BY timestamp ASC '
        'LIMIT 1000',
        ('can', cutoff)
    ).fetchall()

    fft_rows = conn.execute(
        'SELECT timestamp, dominant_freq, latency_ms FROM fft_results '
        'WHERE timestamp > ? ORDER BY timestamp ASC LIMIT 1000',
        (cutoff,)
    ).fetchall()

    conn.close()

    return JSONResponse({
        'modbus': [{'t': r['timestamp'], **json.loads(r['data_json'])} for r in modbus_rows],
        'can':    [{'t': r['timestamp'], **json.loads(r['data_json'])} for r in can_rows],
        'fft':    [{'t': r['timestamp'], 'dominant_freq': r['dominant_freq'],
                    'latency_ms': r['latency_ms']} for r in fft_rows],
    })


@router.get('/api/anomalies')
async def get_anomalies(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT timestamp, rule, severity, reason, data_json '
        'FROM anomaly_events ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return JSONResponse([{
        'timestamp': r[0],
        'time_str':  datetime.fromtimestamp(r[0]).strftime('%H:%M:%S'),
        'rule':      r[1],
        'severity':  r[2],
        'reason':    r[3],
        'data':      json.loads(r[4]),
    } for r in rows])