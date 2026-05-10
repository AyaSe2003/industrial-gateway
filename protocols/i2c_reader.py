#Runs on CPU Core 2
#Reads MPU6050 accelerometer at 1000 Hz
#Sends 1-second batches (1000 samples) to the shared queue for FFT
 
import smbus2
import struct
import time
import os
import logging
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log=logging.getLogger('I2C-Core2')
 
I2C_BUS=0      #/dev/i2c-0
MPU6050_ADDR=0x68   #AD0 pin connected to GND
 
#MPU6050 register map
REG_PWR_MGMT_1=0x6B  #Power management =>  0 to wake chip
REG_SMPLRT_DIV=0x19  #Sample rate divider =>  7 for 1000 Hz
REG_ACCEL_CONFIG=0x1C  #Accelerometer config =>  0 for +/-2g
REG_ACCEL_XOUT_H=0x3B  #First mpu6050 data register (6 bytes follow)
 
ACCEL_SCALE=16384.0    # LSB per g at +/-2g range
TARGET_HZ=1000       #Target sample rate
LOOP_PERIOD=1.0 / TARGET_HZ   #Set 1 ms for 1000 Hz
 
 
def init_mpu6050(bus):
    """Wake up the MPU6050 and configure it for 1000 Hz, +/-2g."""
    bus.write_byte_data(MPU6050_ADDR,REG_PWR_MGMT_1, 0x00)
    time.sleep(0.1) 
 
    #Set sample rate: 8000 / (1 + 7) = 1000 Hz
    bus.write_byte_data(MPU6050_ADDR,REG_SMPLRT_DIV, 7)
 
    #Set accelerometer range to +/-2g (most sensitive)
    bus.write_byte_data(MPU6050_ADDR,REG_ACCEL_CONFIG, 0x00)
 
    log.info('MPU6050 ready: 1000 Hz sample rate,+/-2g range')
 

def read_accel_raw(bus):
    """Read one accelerometer sample. Returns (ax, ay, az) in g units."""
    raw=bus.read_i2c_block_data(MPU6050_ADDR,REG_ACCEL_XOUT_H, 6)
    ax,ay,az=struct.unpack('>hhh',bytes(raw)) #unpack 3 signed 16-bit integers
    return ax / ACCEL_SCALE,ay / ACCEL_SCALE,az / ACCEL_SCALE
 
 
def read_i2c(queue, stop_event):
    """
    Main loop. Launched by main.py as a separate Process.
 
    queue      -- multiprocessing.Queue shared with all cores
    stop_event -- multiprocessing.Event; set by main.py to stop cleanly
    """
    #Pin this process to CPU Core 2
    os.sched_setaffinity(0,{2})
    log.info('Pinned to CPU Core 2')
 
    bus=smbus2.SMBus(I2C_BUS)
    init_mpu6050(bus)
 
    accel_buffer=[]   #Accumulates 1000 samples over 1 second
    last_flush=time.time()
    total_samples=0
 
    while not stop_event.is_set():
        loop_start=time.perf_counter() #more precise than time.time() for measuring short intervals
 
        #Read one sample
        try:
            ax,ay,az=read_accel_raw(bus)
            accel_buffer.append({
                'ax': round(ax, 5),
                'ay': round(ay, 5),
                'az': round(az, 5),
            })
            total_samples+=1
 
        except Exception as e:
            log.warning(f'MPU6050 read error: {e}')
 
        #Flush buffer to queue every 1 second 
        now=time.time()
        if now-last_flush >= 1.0 and accel_buffer:
            queue.put({
                'timestamp':    now,
                'source':       'mpu6050',
                'sample_count': len(accel_buffer),
                'sample_rate':  TARGET_HZ,
                'accel_buffer': accel_buffer.copy(),
            })
            log.info(
                f'{len(accel_buffer)} samples sent to queue '
                f'(total: {total_samples})'
            )
            accel_buffer.clear()
            last_flush = now
 
        #Sleep to maintain 1000 Hz 
        elapsed=time.perf_counter() - loop_start
        sleep_time=max(0.0, LOOP_PERIOD - elapsed)
        time.sleep(sleep_time)
 
    log.info(f'Stopping. Total samples collected: {total_samples}')
    bus.close()
