import smtplib
from email.message import EmailMessage
import time

SMTP_HOST='smtp.gmail.com'
SMTP_PORT=587
SENDER_EMAIL='aya.sellami.010503@gmail.com'       
SENDER_PASS='cgtd folt cykh kelb'  
RECEIVER_EMAIL='aya.sellami.010503@gmail.com' 

EMAIL_COOLDOWN_SEC=3600  
_last_sent={}   

def send_alert(rule,severity,reason):
    now=time.time()
    last=_last_sent.get(rule, 0)

    if now-last<EMAIL_COOLDOWN_SEC:
        remaining= int((EMAIL_COOLDOWN_SEC - (now - last)) / 60)
        print(f'[Email] Skipping {rule}: cooldown active ({remaining} min remaining)')
        return False

    subject_prefix = 'CRITICAL' if severity == 'HIGH' else 'Warning'
    msg = EmailMessage()
    msg['Subject']= f'{subject_prefix}: Industrial Gateway: {rule}'
    msg['From']= SENDER_EMAIL
    msg['To']= RECEIVER_EMAIL
    msg.set_content(f'''
Gateway alert triggered:

Severity : {severity}
Type     : {rule}
Details  : {reason}

Check the dashboard for more information.
http://<Odroid IP>:8000/
''')
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(SENDER_EMAIL, SENDER_PASS)
            smtp.send_message(msg)
        _last_sent[rule]=now
        print(f'[Email] Sent {rule} alert')
        return True
    except Exception as e:
        print(f'[Email] Failed: {e}')
        return False