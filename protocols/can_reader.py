import can
import time
import os
import logging
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('CAN-Core1')
 
# Configuration
CAN_INTERFACE= 'can0'
MACHINE_FRAME_ID= 0x100   
LOG_EVERY= 100     
 
def decode_frame(msg):
    """
    Convert a raw python-can Message into a structured dict.
    msg.data is a bytearray
    """
    # Bytes 0 and 1: RPM stored big-endian
    # (high byte << 8) OR low byte gives the full 16-bit value
    rpm= (msg.data[0] << 8) | msg.data[1]
 
    direction= 'rising' if msg.data[2] == 0x01 else 'falling'
 
    status_codes= {0x00: 'normal', 0x01: 'warning', 0x02: 'fault'}
    status= status_codes.get(msg.data[3], 'unknown')
 
    return {
        'timestamp': time.time(),
        'source':'can',
        'frame_id':hex(msg.arbitration_id),
        'rpm': rpm,
        'direction': direction,
        'status':status,
    }
 
 
def read_can(queue, stop_event):
    """
    Entry point called by main.py as a separate Process.
    queue      -- multiprocessing.Queue shared across all cores
    stop_event -- multiprocessing.Event set by main.py on shutdown
    """
    # Pin to CPU Core 1
    os.sched_setaffinity(0, {1})
    log.info('Pinned to CPU Core 1')
 
    try:
        # cmd: sudo ip link set can0 up type can bitrate 500000
        bus = can.interface.Bus(channel=CAN_INTERFACE, bustype='socketcan')
        log.info(f'Listening on {CAN_INTERFACE}')
    except Exception as e:
        log.error(f'Cannot open {CAN_INTERFACE}: {e}')
        log.error('Fix: sudo ip link set can0 up type can bitrate 500000')
        return
 
    frame_count=0
    error_count=0
 
    while not stop_event.is_set():
        try:
            # recv() blocks until a frame arrives or timeout expires.
            # timeout=1.0 => check stop_event every second at most.
            msg=bus.recv(timeout=1.0)
 
            if msg is None:
                continue   # Timeout expired loop back to check stop_event
 
            # Only process frames with this machine status ID.
            # Other IDs from other nodes on the bus are silently ignored.
            if msg.arbitration_id==MACHINE_FRAME_ID:
                data=decode_frame(msg)
                queue.put(data)
                frame_count += 1
 
                if frame_count%LOG_EVERY==0:
                    log.info(
                        f'Frame #{frame_count}: '
                        f'RPM={data["rpm"]}  '
                        f'Dir={data["direction"]}  '
                        f'Status={data["status"]}'
                    )
 
        except Exception as e:
            log.error(f'CAN recv error: {e}')
            error_count += 1
            if error_count > 10:
                log.error('Too many errors => stopping CAN reader')
                break
            time.sleep(0.5)
 
    log.info(f'Stopping. Frames received: {frame_count}  Errors: {error_count}')
    bus.shutdown()
