#!/usr/bin/env python3
# test_performance.py
# Run from ~/industrial_gateway with main.py already running
# Usage: python3 test_performance.py

import sqlite3
import time
import os

DB_PATH = os.path.expanduser('~/industrial_gateway/gateway.db')
WINDOW_DURATION = 60   # seconds per observation window
NUM_WINDOWS     = 3    # number of windows to measure

def measure_window(window_num):
    """
    Wait WINDOW_DURATION seconds then query the DB
    for FFT stats in that window.
    """
    print(f'\n--- Window {window_num} ---')
    print(f'Measuring for {WINDOW_DURATION} seconds...')

    t_start = time.time()
    time.sleep(WINDOW_DURATION)
    t_end   = time.time()

    conn = sqlite3.connect(DB_PATH)

    # FFT count in this window
    fft_count = conn.execute(
        'SELECT COUNT(*) FROM fft_results '
        'WHERE timestamp >= ? AND timestamp <= ?',
        (t_start, t_end)
    ).fetchone()[0]

    # Average latency
    avg_lat = conn.execute(
        'SELECT AVG(latency_ms) FROM fft_results '
        'WHERE timestamp >= ? AND timestamp <= ?',
        (t_start, t_end)
    ).fetchone()[0] or 0.0

    # Max latency
    max_lat = conn.execute(
        'SELECT MAX(latency_ms) FROM fft_results '
        'WHERE timestamp >= ? AND timestamp <= ?',
        (t_start, t_end)
    ).fetchone()[0] or 0.0

    # Min latency
    min_lat = conn.execute(
        'SELECT MIN(latency_ms) FROM fft_results '
        'WHERE timestamp >= ? AND timestamp <= ?',
        (t_start, t_end)
    ).fetchone()[0] or 0.0

    # Average dominant frequency
    avg_freq = conn.execute(
        'SELECT AVG(dominant_freq) FROM fft_results '
        'WHERE timestamp >= ? AND timestamp <= ?',
        (t_start, t_end)
    ).fetchone()[0] or 0.0

    conn.close()

    rate = fft_count / WINDOW_DURATION

    print(f'  FFT count       : {fft_count}')
    print(f'  Rate            : {rate:.2f} FFT/s')
    print(f'  Avg latency     : {avg_lat:.3f} ms')
    print(f'  Max latency     : {max_lat:.3f} ms')
    print(f'  Min latency     : {min_lat:.3f} ms')
    print(f'  Avg dominant freq: {avg_freq:.2f} Hz')

    return {
        'window':    window_num,
        'fft_count': fft_count,
        'rate':      rate,
        'avg_lat':   avg_lat,
        'max_lat':   max_lat,
        'min_lat':   min_lat,
        'avg_freq':  avg_freq,
    }


def measure_anomaly_counts():
    """Count anomaly events recorded in the DB."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT rule, severity, COUNT(*) as cnt '
        'FROM anomaly_events '
        'GROUP BY rule, severity'
    ).fetchall()
    conn.close()
    return rows


def measure_queue_health():
    """
    Check sensor_readings row counts per source
    to confirm all three data sources are active.
    """
    conn = sqlite3.connect(DB_PATH)
    cutoff = time.time() - WINDOW_DURATION
    rows = conn.execute(
        'SELECT source, COUNT(*) FROM sensor_readings '
        'WHERE timestamp > ? GROUP BY source',
        (cutoff,)
    ).fetchall()
    conn.close()
    return rows


def print_summary(results):
    """Print the final summary table."""
    print('\n')
    print('=' * 65)
    print(' PERFORMANCE SUMMARY — FFT Processor')
    print('=' * 65)
    print(f"{'Window':<10} {'Count':<10} {'Rate (FFT/s)':<15} "
          f"{'Avg Lat (ms)':<15} {'Max Lat (ms)':<15}")
    print('-' * 65)

    total_count = 0
    total_rate  = 0.0
    total_avg   = 0.0
    total_max   = 0.0

    for r in results:
        print(f"{r['window']:<10} {r['fft_count']:<10} "
              f"{r['rate']:<15.2f} {r['avg_lat']:<15.3f} "
              f"{r['max_lat']:<15.3f}")
        total_count += r['fft_count']
        total_rate  += r['rate']
        total_avg   += r['avg_lat']
        total_max    = max(total_max, r['max_lat'])

    n = len(results)
    print('-' * 65)
    print(f"{'Mean':<10} {total_count//n:<10} "
          f"{total_rate/n:<15.2f} {total_avg/n:<15.3f} "
          f"{total_max:<15.3f}")
    print(f"{'Requirement':<10} {'---':<10} "
          f"{'≥ 4.0':<15} {'---':<15} {'< 100':<15}")
    print('=' * 65)

    # Pass/Fail
    mean_rate = total_rate / n
    mean_avg  = total_avg  / n
    print('\n PASS / FAIL')
    print('-' * 40)
    print(f'  FFT rate ≥ 4.0 FFT/s : '
          f'{"PASS" if mean_rate >= 4.0 else "FAIL"} '
          f'({mean_rate:.2f} FFT/s)')
    print(f'  Avg latency < 100 ms  : '
          f'{"PASS" if mean_avg < 100 else "FAIL"} '
          f'({mean_avg:.3f} ms)')
    print(f'  Max latency < 100 ms  : '
          f'{"PASS" if total_max < 100 else "FAIL"} '
          f'({total_max:.3f} ms)')
    print('=' * 65)


def main():
    print('=' * 65)
    print(' Industrial Gateway — Performance Test')
    print(f' DB path : {DB_PATH}')
    print(f' Windows : {NUM_WINDOWS} x {WINDOW_DURATION}s')
    print('=' * 65)

    # Confirm DB exists
    if not os.path.exists(DB_PATH):
        print(f'\nERROR: Database not found at {DB_PATH}')
        print('Make sure main.py is running first.')
        return

    # Warm-up wait — let FFT baseline establish
    print('\nWaiting 15 seconds for system warm-up and '
          'FFT baseline to establish...')
    time.sleep(15)

    # Run measurement windows
    results = []
    for i in range(1, NUM_WINDOWS + 1):
        results.append(measure_window(i))

    # Print FFT summary table
    print_summary(results)

    # Data source health check
    print('\n DATA SOURCE ACTIVITY (last 60 seconds)')
    print('-' * 40)
    for source, count in measure_queue_health():
        print(f'  {source:<12}: {count} rows written to DB')

    # Anomaly summary
    print('\n ANOMALY EVENTS RECORDED')
    print('-' * 40)
    anomalies = measure_anomaly_counts()
    if anomalies:
        for rule, severity, count in anomalies:
            print(f'  [{severity}] {rule}: {count} events')
    else:
        print('  None recorded yet')

    print('\nDone. Copy the PERFORMANCE SUMMARY table into your report.')


if __name__ == '__main__':
    main()