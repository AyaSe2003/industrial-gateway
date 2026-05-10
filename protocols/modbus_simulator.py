import time,os,random,logging

logging.basicConfig(level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s', datefmt='%H:%M:%S')
log=logging.getLogger('Modbus-Core0')

POLL_PERIOD=0.5  # 2 Hz
SPIKE_EVERY=50       # every 50 readings (25 seconds)
SPIKE_DURATION=6 # last 6 readings (3 seconds)
STARTUP_READS=10   # first 10 readings (5 seconds) are critical

def read_modbus(queue,stop_event):
    os.sched_setaffinity(0,{0})
    log.info('Pinned to CPU Core 0: Modbus simulator running')

    rpm=1200
    rpm_up=True
    temp_c=22.5
    count=0
    spike_countdown=0

    while not stop_event.is_set():
        poll_start=time.time()

        # Startup spike=> first STARTUP_READS readings are critical
        if count<STARTUP_READS:
            temp_c=random.uniform(41.0,45.0)
            rpm=3600
            status='warning'

        else:
            # Normal RPM sweep
            if rpm_up:
                rpm += 25
                if rpm >= 3000:rpm_up = False
            else:
                rpm -= 25
                if rpm <= 0: rpm_up = True

            # Periodic temperature spike
            if count >0 and count % SPIKE_EVERY == 0:
                spike_countdown=SPIKE_DURATION
                log.info('*** Temperature spike starting ***')

            if spike_countdown > 0:
                temp_c = random.uniform(41.0,45.0)
                spike_countdown -= 1
            else:
                temp_c += random.uniform(-0.5,0.5)
                temp_c = max(18.0,min(38.0,temp_c))

            status ='warning' if rpm>2700 else 'normal'

        data = {
            'timestamp':time.time(),
            'source':'modbus',
            'rpm':rpm,
            'temperature':round(temp_c, 1),
            'status':status,
        }
        queue.put(data)
        count += 1
        log.info(f'#{count}:RPM={rpm} Temp={temp_c:.1f}C Status={status}')

        elapsed=time.time()-poll_start
        time.sleep(max(0,POLL_PERIOD-elapsed))

    log.info(f'Stopping.Total reads:{count}')