#Modbus RTU master => runs on CPU Core 0
#Polls Arduino 1 via MAX485 on /dev/ttyS1 at 2 Hz
 
import time
import os
import logging
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('Modbus-Core0')
 
#Configuration
SERIAL_PORT= '/dev/ttyS1'   # UART2 on ODROID-N2+
BAUD_RATE= 9600           # Must match Arduino modbus.begin(1, 9600)
SLAVE_ID= 1              # Must match Arduino modbus.begin(1, ...)
POLL_PERIOD=0.5            # Seconds between polls = 2 Hz
 
 
def read_modbus(queue, stop_event):
    """
    Entry point called by main.py as a separate Process.
    queue      -- multiprocessing.Queue for passing data to other cores
    stop_event -- multiprocessing.Event; set by main.py on Ctrl+C
    """
    #Pin this process to CPU Core 0.
    os.sched_setaffinity(0, {0})
    log.info('Pinned to CPU Core 0')
 
    client = ModbusSerialClient(
        port= SERIAL_PORT,
        baudrate= BAUD_RATE,
        parity= 'N',    # No parity bit
        stopbits=1,      # 1 stop bit
        bytesize=8,      # 8 data bits 
        timeout =1,       # 1 second timeout per request
	    rtscts= False,
        rts_level_for_tx= True,
        rts_level_for_rx= False,
    )
 
    if not client.connect():
        log.error(f'Cannot open {SERIAL_PORT}.')
        log.error('Check: overlays=uart2 in /boot/config.ini, user in dialout group')
        return
 
    log.info(f'Connected to {SERIAL_PORT} at {BAUD_RATE} baud')
 
    read_count= 0
    error_count =0
 
    while not stop_event.is_set():
        poll_start = time.time()
 
        try:
            #Read 3 holding registers starting at address 0:
            #[0]=RPM, [1]= Temperaturex10, [2]= Status
            result = client.read_holding_registers(
                address=0, count=3, slave=SLAVE_ID
            )
 
            if result.isError():
                log.warning(f'Modbus error: {result}')
                error_count += 1
            else:
                rpm= result.registers[0]
                temperature= result.registers[1] / 10.0   #Undo the x10 encoding
                status_raw =result.registers[2]
                status={0:'normal', 1:'warning', 2:'fault'}.get(status_raw, 'unknown')
 
                data = {
                    'timestamp':time.time(),
                    'source': 'modbus',
                    'rpm':rpm,
                    'temperature':temperature,
                    'status': status,
                }
                queue.put(data)
                read_count += 1
                error_count=0   #Reset error streak on success
 
                log.info(
                    f'Read #{read_count}: RPM={rpm}  '
                    f'Temp={temperature}C  Status={status}'
                )
 
        except ModbusException as e:
            log.error(f'Modbus exception: {e}')
            error_count += 1
        except Exception as e:
            log.error(f'Unexpected error: {e}')
            error_count+= 1
 
        #Wait to maintain exactly 2 Hz.
        #Subtract the time already spent on the read operation.
        elapsed = time.time()-poll_start
        time.sleep(max(0,POLL_PERIOD- elapsed))
 
    log.info(f'Stopping. Reads: {read_count}  Errors: {error_count}')
    client.close()
