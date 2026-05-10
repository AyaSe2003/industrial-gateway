import time,os,logging

logging.basicConfig(level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('CAN-Core1')

FRAME_PERIOD=0.01   # 100 Hz
LOG_EVERY=100  # log every 100 frames (10 seconds)
SPIKE_EVERY=10000      # every 10,000 frames (100 seconds)
SPIKE_DURATION=500  # last 500 frames (5 seconds)
STARTUP_FRAMES=1000   # first 1000 frames (10 seconds) are critical

def read_can(queue,stop_event):
    os.sched_setaffinity(0,{1})
    log.info('Pinned to CPU Core 1: CAN simulator running')

    rpm=1200
    rpm_up=True
    frame_count=0
    spike_countdown=0

    while not stop_event.is_set():
        frame_start=time.perf_counter()

        if frame_count<STARTUP_FRAMES:
            # Startup spike — critical RPM
            rpm = 3600
            direction='rising'
            status='critical'

        else:
            # Periodic RPM spike
            if frame_count > 0 and frame_count % SPIKE_EVERY == 0: 
                spike_countdown=SPIKE_DURATION
                log.info(f'*** RPM spike starting at frame #{frame_count} ***')

            if spike_countdown>0:
                rpm = 3600
                spike_countdown-=1
            else:
                if rpm_up:
                    rpm += 50
                    if rpm >= 3000: rpm_up=False
                else:
                    rpm-=50
                    if rpm <= 0: rpm_up=True

            direction='rising' if rpm_up else 'falling'
            if rpm > 3200:
                status = 'critical'
            elif rpm > 2700:
                status = 'warning'
            else:
                status = 'normal'

        data = {
            'timestamp':time.time(),
            'source':'can',
            'frame_id':'0x100',
            'rpm':rpm,
            'direction':direction,
            'status':status,
        }
        queue.put(data)
        frame_count +=1

        if frame_count % LOG_EVERY == 0:
            log.info(f'Frame #{frame_count}: RPM={rpm}  Dir={direction}  Status={status}')

        elapsed=time.perf_counter() - frame_start
        time.sleep(max(0,FRAME_PERIOD-elapsed))

    log.info(f'Stopping.Total frames: {frame_count}')