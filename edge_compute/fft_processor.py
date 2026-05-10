# FFT processor: runs on CPU Core 3
 
import numpy as np
import time
import os
import logging
from collections import deque
 
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log=logging.getLogger('FFT-Core3')
 
#FFT configuration 
SAMPLE_RATE=1000     
FFT_WINDOW=256      # Samples per FFT=> spec says 256 must be power of 2
OVERLAP=128     # 50% overlap to achieve ≥4 FFT/s
STEP=FFT_WINDOW-OVERLAP   # 128 new samples per FFT
 
# Frequency axis: pre-computed once,reused every FFT
# rfftfreq returns N//2 + 1 frequency bins for a real-valued input of length N
FREQ_AXIS=np.fft.rfftfreq(FFT_WINDOW,d=1.0 / SAMPLE_RATE)
 
# Hanning window: multiplied with the signal before FFT
# Why: without windowing, a signal that doesn't start/end at zero
# creates artificial high-frequency components (spectral leakage).
# The Hanning window tapers the edges smoothly, eliminating this artefact.
HANNING=np.hanning(FFT_WINDOW)
 
 
def compute_fft(samples_z):
    """
    Run one FFT on a 256-sample Z-axis window.
    Returns (dominant_freq_hz, amplitudes_array, latency_ms).
    """
    t_start=time.perf_counter()
 
    # Convert list to numpy array for vectorised operations
    window=np.array(samples_z, dtype = np.float32)
 
    # Apply Hanning window to reduce spectral leakage
    windowed=window * HANNING
 
    # rfft: real-valued FFT=>  Faster than fft() for real inputs.
    # Returns N//2+1 = 129 complex values.
    fft_complex=np.fft.rfft(windowed)
 
    # Amplitude at each frequency bin
    # We normalise by FFT_WINDOW so amplitude is independent of window size
    amplitudes=np.abs(fft_complex) / FFT_WINDOW
 
    # Skip bin 0 (DC component = average offset, not a vibration frequency)
    # Find the bin with highest amplitude starting from index 1
    dominant_bin=np.argmax(amplitudes[1:])+1
    dominant_freq=float(FREQ_AXIS[dominant_bin])
 
    latency_ms=(time.perf_counter() - t_start) * 1000
    return dominant_freq,amplitudes.tolist(),latency_ms
 
 
def run_fft(queue_in,queue_out, stop_event):
    """
    Main loop. Launched by main.py as a separate Process on Core 3.
 
    queue_in   -- reads mpu6050 batches from here (shared input queue)
    queue_out  -- puts fft_result dicts here (shared output queue)
    stop_event -- multiprocessing.Event; set by main.py on shutdown
    """
    os.sched_setaffinity(0, {3})
    log.info('Pinned to CPU Core 3')
    log.info(f'FFT config: window={FFT_WINDOW} samples, overlap={OVERLAP}, Fs={SAMPLE_RATE} Hz')
    log.info(f'Frequency resolution: {SAMPLE_RATE / FFT_WINDOW:.2f} Hz per bin')
 
    # Sliding window buffer: holds up to FFT_WINDOW samples
    # deque with maxlen automatically discards oldest when full
    window_buffer=deque(maxlen=FFT_WINDOW)
 
    fft_count=0
    total_latency=0
 
    while not stop_event.is_set():
        try:
            item=queue_in.get(timeout=2.0)
 
            if item.get('source') != 'mpu6050':
                # Put non-MPU6050 data into the output queue unchanged
                queue_out.put(item)
                continue
 
            # Extract Z-axis values from the batch
            # accel_buffer is a list of dicts: [{'ax':..,'ay':..,'az':..}, ...]
            new_z_samples=[s['az'] for s in item['accel_buffer']]
 
            # Add new samples to the sliding window
            window_buffer.extend(new_z_samples)
 
            # Run FFT as long as we have a full window
            while len(window_buffer)>=FFT_WINDOW:
                # Take the most recent FFT_WINDOW samples
                samples=list(window_buffer)[-FFT_WINDOW:]
 
                dominant_freq,amplitudes,latency_ms=compute_fft(samples)
                fft_count +=1
                total_latency+=latency_ms
 
                # Build result dict and push to output queue
                result={
                    'timestamp':time.time(),
                    'source':'fft',
                    'dominant_freq':round(dominant_freq, 2),
                    'amplitudes':amplitudes,   # full spectrum for dashboard
                    'freq_axis':FREQ_AXIS.tolist(),
                    'fft_count':fft_count,
                    'latency_ms':round(latency_ms, 3),
                    'window_size':FFT_WINDOW,
                    'sample_rate':SAMPLE_RATE,
                }
                queue_out.put(result)
 
                # Log every 4 FFTs (1 second of results)
                if fft_count % 4 == 0:
                    avg_lat = total_latency / fft_count
                    log.info(
                        f'FFT #{fft_count}: dominant={dominant_freq:.1f} Hz  '
                        f'latency={latency_ms:.2f}ms  avg={avg_lat:.2f}ms'
                    )
 
                # Slide the window forward by STEP samples
                # Remove the oldest STEP samples from the left of the buffer
                for _ in range(STEP):
                    if window_buffer:
                        window_buffer.popleft()
 
        except Exception as e:
            if 'Empty' not in str(type(e).__name__):
                log.error(f'FFT error: {e}')
 
    avg_lat = (total_latency/fft_count) if fft_count>0 else 0
    log.info(f'Stopping. FFTs computed: {fft_count}  Avg latency: {avg_lat:.2f}ms')
