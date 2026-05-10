#   vibration frequency deviation > 10% from baseline
#   Temp > 40°C or RPM > 3500
 
from asyncio import events
import time
import os
import logging
from notifications.email_alert import send_alert
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('Anomaly-Core4')
 
# Anomaly thresholds
FREQ_DEVIATION_THRESHOLD=5   
TEMP_MAX=40   # °C 
RPM_MAX=3500   # RPM 
BASELINE_SAMPLE_COUNT=10     
 
# Prevents flooding the queue with repeated alerts for one sustained fault
ANOMALY_COOLDOWN_SEC= 30
 
 
class AnomalyDetector:
    """
    Stateful anomaly detector.
    Tracks baseline frequency and last anomaly times per rule.
    """
 
    def __init__(self):
        # Frequency baseline 
        self.baseline_freq=None
        self.baseline_samples=[]   # accumulates readings until baseline is set
        
        # Track when each anomaly type was last raised 
        self.last_anomaly_time= {
            'freq_deviation':0,
            'temp_high':0,
            'rpm_high': 0,
            'can_warning':0,
            'can_fault':0,
        }
 
        self.anomaly_count=0
        self.prev_can_status= 'normal'  # Track previous CAN status to detect changes
        self.prev_rpm_over_limit=False
 
    def _can_raise(self,rule_key):
        """Return True if enough time has passed since last anomaly of this type."""
        return (time.time() - self.last_anomaly_time[rule_key]) > ANOMALY_COOLDOWN_SEC
 
    def _raise_anomaly(self,rule_key, severity, reason,data):
        """Build an anomaly event dict and mark the cooldown timestamp."""
        self.last_anomaly_time[rule_key]=time.time()
        self.anomaly_count +=1
        event = {
            'timestamp':time.time(),
            'source':'anomaly',
            'rule': rule_key,
            'severity':severity,     # 'HIGH' or 'MEDIUM'
            'reason':reason,        # human-readable description
            'data':data,          # the raw values that triggered it
            'anomaly_id':self.anomaly_count,
        }
        log.warning(f'[{severity}] {reason}')
        send_alert(rule_key, severity, reason)
        return event
 
    def check_fft(self,item):
        """
        check dominant frequency against baseline.
        Returns an anomaly event dict, or None if no anomaly.
        """
        freq=item['dominant_freq']
 
        # Phase 1: build baseline 
        if self.baseline_freq is None:
            self.baseline_samples.append(freq)
            log.info(
                f'Baseline sample {len(self.baseline_samples)}/{BASELINE_SAMPLE_COUNT}: '
                f'{freq:.2f} Hz'
            )
            if len(self.baseline_samples) >= BASELINE_SAMPLE_COUNT:
                self.baseline_freq = sum(self.baseline_samples) / len(self.baseline_samples)
                log.info(f'Baseline established: {self.baseline_freq:.2f} Hz')
            return None   
        # Phase 2: check deviation 
        deviation_pct=abs(freq - self.baseline_freq) / self.baseline_freq * 100
 
        if deviation_pct > FREQ_DEVIATION_THRESHOLD:
            if self._can_raise('freq_deviation'):
                return self._raise_anomaly(
                    rule_key='freq_deviation',
                    severity='HIGH',
                    reason = (
                        f'Vibration frequency {freq:.1f} Hz deviates '
                        f'{deviation_pct:.1f}% from baseline {self.baseline_freq:.1f} Hz'
                    ),
                    data = {
                        'current_freq':freq,
                        'baseline_freq':self.baseline_freq,
                        'deviation_pct':round(deviation_pct, 2),
                    }
                )
        return None
 
    def check_modbus(self,item):
        """
        check temperature and RPM from Modbus data.
        Returns list of anomaly events (could be 0, 1, or 2).
        """
        events=[]
 
        # Temperature check
        temp = item.get('temperature', 0)
        if temp > TEMP_MAX and self._can_raise('temp_high'):
            events.append(self._raise_anomaly(
                rule_key= 'temp_high',
                severity='MEDIUM',
                reason=f'Temperature {temp:.1f}°C exceeds limit of {TEMP_MAX}°C',
                data={'temperature': temp, 'limit': TEMP_MAX}
            ))
 
        # RPM check 
        rpm = item.get('rpm', 0)
        if rpm > RPM_MAX and self._can_raise('rpm_high'):
            events.append(self._raise_anomaly(
                rule_key= 'rpm_high',
                severity='HIGH',
                reason=f'RPM {rpm} exceeds maximum of {RPM_MAX}',
                data={'rpm': rpm, 'limit': RPM_MAX}
            ))
 
        return events
 
    def check_can(self,item):
        """
        check RPM and status from CAN data.
        Returns list of anomaly events.
        """
        events=[]
 
        # RPM check
        rpm=item.get('rpm', 0)
        rpm_over=rpm> RPM_MAX
        if rpm_over and not self.prev_rpm_over_limit and self._can_raise('rpm_high'):
            events.append(self._raise_anomaly(
                rule_key= 'rpm_high',
                severity='HIGH',
                reason=f'CAN RPM {rpm} exceeds maximum of {RPM_MAX}',
                data={'rpm': rpm, 'limit': RPM_MAX}
            ))
        self.prev_rpm_over_limit = rpm_over
 
        #Status byte check
        status=item.get('status','normal')
        if status!=self.prev_can_status:
            if status=='warning' and self._can_raise('can_warning'):
                events.append(self._raise_anomaly(
                    rule_key='can_warning',
                    severity='MEDIUM',
                    reason=f'CAN node reporting warning status',
                    data={'status': status, 'rpm': rpm}
                ))
            elif status=='fault' and self._can_raise('can_fault'):
                events.append(self._raise_anomaly(
                    rule_key='can_fault',
                    severity='HIGH',
                    reason=f'CAN node reporting FAULT status',
                    data={'status': status, 'rpm': rpm}
                ))
        self.prev_can_status=status
        return events
 
 
def run_anomaly_detector(queue_in,queue_out,stop_event):
    """
    Main loop. Launched by main.py as a separate Process on Core 4.
 
    queue_in   -- reads fft/modbus/can data from here
    queue_out  -- puts anomaly events AND all forwarded data here
    stop_event -- multiprocessing.Event set by main.py on shutdown
    """
    os.sched_setaffinity(0,{4})
    log.info('Pinned to CPU Core 4')
    log.info(
        f'Thresholds: freq_deviation>{FREQ_DEVIATION_THRESHOLD}%  '
        f'temp>{TEMP_MAX}C  rpm>{RPM_MAX}'
    )
 
    detector=AnomalyDetector()
    processed=0
 
    while not stop_event.is_set():
        try:
            item= queue_in.get(timeout=2.0)
            processed +=1
            src= item.get('source', '')
 
            anomaly_events=[]
 
            if src=='fft':
                event=detector.check_fft(item)
                if event:
                    anomaly_events.append(event)
 
            elif src=='modbus':
                anomaly_events.extend(detector.check_modbus(item))
 
            elif src == 'can':
                anomaly_events.extend(detector.check_can(item))
 
            # Forward the original data to the output queue
            queue_out.put(item)
 
            for event in anomaly_events:
                queue_out.put(event)
 
        except Exception as e:
            if 'Empty' not in str(type(e).__name__):
                log.error(f'Detector error: {e}')
 
    log.info(
        f'Stopping.Items processed:{processed}  '
        f'Anomalies raised:{detector.anomaly_count}'
    )
