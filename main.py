import multiprocessing as mp
import threading, signal, time, logging

from protocols.modbus_simulator    import read_modbus   
from protocols.can_simulator       import read_can      
from protocols.i2c_reader          import read_i2c      
from edge_compute.fft_processor    import run_fft       
from edge_compute.anomaly_detector import run_anomaly_detector
from database.sqlite_logger        import run_logger    
from web.server                    import run_server    

logging.basicConfig(level=logging.INFO,
    format='[MAIN %(asctime)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('Main')

def fanout_thread(queue_out, queue_ws, stop_event):
    while not stop_event.is_set() or not queue_out.empty():
        try:
            item = queue_out.get(timeout=1.0)
            queue_ws.put_nowait(item)
        except Exception:
            continue

def main():
    log.info('=== Industrial Gateway ===')
    log.info('Cores 0-5: Modbus-sim | CAN-sim | I2C | FFT | Anomaly | WebSocket')

    queue_raw=mp.Queue(maxsize=2000)
    queue_mid=mp.Queue(maxsize=2000)
    queue_out=mp.Queue(maxsize=2000)
    queue_ws=mp.Queue(maxsize=500)
    stop_event=mp.Event()

    processes=[
        mp.Process(target=read_modbus,args=(queue_raw, stop_event),name='Modbus-Core0',daemon=True),
        mp.Process(target=read_can,args=(queue_raw,stop_event),name='CAN-Core1',daemon=True),
        mp.Process(target=read_i2c,args=(queue_raw,stop_event),name='I2C-Core2',daemon=True),
        mp.Process(target=run_fft,args=(queue_raw,queue_mid, stop_event),name='FFT-Core3',daemon=True),
        mp.Process(target=run_anomaly_detector, args=(queue_mid, queue_out, stop_event),name='Anomaly-Core4',daemon=True),
        mp.Process(target=run_server,args=(queue_ws,stop_event),name='Web-Core5',daemon=True),
    ]

    logger_thread=threading.Thread(target=run_logger,
        args=(queue_out,stop_event),name='SQLite-Logger',daemon=True)
    fanout=threading.Thread(target=fanout_thread,
        args=(queue_out, queue_ws, stop_event),name='Fan-Out',daemon=True)

    for proc in processes:
        proc.start()
        log.info(f'Started {proc.name}  (PID {proc.pid})')
    logger_thread.start()
    fanout.start()
    log.info('Dashboard: http://192.168.1.13:8000/')
    
    # address = hostname -I

    def shutdown(sig, frame):
        log.info('Shutdown — stopping all workers...')
        stop_event.set()
    signal.signal(signal.SIGINT,  shutdown) #ctrl+c
    signal.signal(signal.SIGTERM, shutdown) #kill command

    while not stop_event.is_set():
        time.sleep(10)
        if not stop_event.is_set():
            log.info(f'Queues — raw:{queue_raw.qsize()}  '
                     f'mid:{queue_mid.qsize()}  out:{queue_out.qsize()}')

    for proc in processes:
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
    logger_thread.join(timeout=10)
    fanout.join(timeout=5)
    log.info('All workers stopped.')

if __name__ == '__main__':
    main()
