"""
Email Notification Service for CareSync Healthcare System.
Supports configurable providers (SendGrid, Mailgun, SMTP, Mock/Console)
with rich HTML email templates and structured delivery responses.
"""

import json
import logging
import smtplib
import time
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Unified Email Dispatcher supporting SendGrid, Mailgun, SMTP, and Mock providers.
    """

    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or settings.EMAIL_PROVIDER).lower()
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        from_email: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Dispatch an email using the configured email provider.
        Returns a dict: {"success": bool, "provider": str, "message_id": str, "error": Optional[str]}
        """
        sender = from_email or self.from_email
        plain_text = text_body or self._strip_html(html_body)

        logger.info(f"[EmailService] Dispatching email to '{to_email}' via provider '{self.provider}' (Subject: {subject})")

        if self.provider == "sendgrid":
            return self._send_via_sendgrid(to_email, subject, html_body, plain_text, sender)
        elif self.provider == "mailgun":
            return self._send_via_mailgun(to_email, subject, html_body, plain_text, sender)
        elif self.provider == "smtp":
            return self._send_via_smtp(to_email, subject, html_body, plain_text, sender)
        else:
            # Default to Mock / Console Provider
            return self._send_via_mock(to_email, subject, html_body, plain_text, sender)

    # -------------------------------------------------------------------------
    # Provider Implementations
    # -------------------------------------------------------------------------

    def _send_via_sendgrid(
        self, to_email: str, subject: str, html_body: str, plain_text: str, sender: str
    ) -> dict[str, Any]:
        """SendGrid v3 REST API implementation."""
        api_key = settings.SENDGRID_API_KEY
        if not api_key:
            logger.warning("[EmailService:SendGrid] Missing SENDGRID_API_KEY. Falling back to Mock delivery.")
            return self._send_via_mock(to_email, subject, html_body, plain_text, sender)

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": sender, "name": self.from_name},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": plain_text},
                {"type": "text/html", "value": html_body}
            ]
        }

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.status
                msg_id = response.headers.get("X-Message-Id", f"sg-{int(time.time()*1000)}")
                if status in (200, 202):
                    logger.info(f"[EmailService:SendGrid] Successfully delivered message {msg_id} to {to_email}")
                    return {"success": True, "provider": "sendgrid", "message_id": msg_id, "error": None}
                else:
                    return {"success": False, "provider": "sendgrid", "message_id": "", "error": f"HTTP {status}"}
        except Exception as e:
            logger.error(f"[EmailService:SendGrid] Delivery failure to {to_email}: {e}")
            return {"success": False, "provider": "sendgrid", "message_id": "", "error": str(e)}

    def _send_via_mailgun(
        self, to_email: str, subject: str, html_body: str, plain_text: str, sender: str
    ) -> dict[str, Any]:
        """Mailgun Messages REST API implementation."""
        api_key = settings.MAILGUN_API_KEY
        domain = settings.MAILGUN_DOMAIN
        if not api_key or not domain:
            logger.warning("[EmailService:Mailgun] Missing MAILGUN_API_KEY or MAILGUN_DOMAIN. Falling back to Mock.")
            return self._send_via_mock(to_email, subject, html_body, plain_text, sender)

        url = f"https://api.mailgun.net/v3/{domain}/messages"
        import base64
        auth_header = "Basic " + base64.b64encode(f"api:{api_key}".encode("utf-8")).decode("utf-8")
        
        form_data = urllib.parse.urlencode({
            "from": f"{self.from_name} <{sender}>",
            "to": to_email,
            "subject": subject,
            "text": plain_text,
            "html": html_body
        }).encode("utf-8")

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            req = urllib.request.Request(url, data=form_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.status
                body = response.read().decode("utf-8")
                data = json.loads(body) if body else {}
                msg_id = data.get("id", f"mg-{int(time.time()*1000)}")
                if status == 200:
                    logger.info(f"[EmailService:Mailgun] Successfully delivered message {msg_id} to {to_email}")
                    return {"success": True, "provider": "mailgun", "message_id": msg_id, "error": None}
                else:
                    return {"success": False, "provider": "mailgun", "message_id": "", "error": f"HTTP {status}"}
        except Exception as e:
            logger.error(f"[EmailService:Mailgun] Delivery failure to {to_email}: {e}")
            return {"success": False, "provider": "mailgun", "message_id": "", "error": str(e)}

    def _send_via_smtp(
        self, to_email: str, subject: str, html_body: str, plain_text: str, sender: str
    ) -> dict[str, Any]:
        """Standard SMTP delivery implementation."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{sender}>"
            msg["To"] = to_email

            part1 = MIMEText(plain_text, "plain", "utf-8")
            part2 = MIMEText(html_body, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.sendmail(sender, [to_email], msg.as_string())
            server.quit()

            msg_id = f"smtp-{int(time.time()*1000)}"
            logger.info(f"[EmailService:SMTP] Delivered email to {to_email} with ID {msg_id}")
            return {"success": True, "provider": "smtp", "message_id": msg_id, "error": None}
        except Exception as e:
            logger.error(f"[EmailService:SMTP] SMTP delivery failed to {to_email}: {e}")
            return {"success": False, "provider": "smtp", "message_id": "", "error": str(e)}

    def _send_via_mock(
        self, to_email: str, subject: str, html_body: str, plain_text: str, sender: str
    ) -> dict[str, Any]:
        """Mock / Local Console Delivery Provider."""
        msg_id = f"mock-msg-{int(time.time()*1000)}"
        logger.info(
            f"\n"
            f"========================= [MOCK EMAIL DISPATCH] =========================\n"
            f"Provider   : MOCK / CONSOLE\n"
            f"To         : {to_email}\n"
            f"From       : {self.from_name} <{sender}>\n"
            f"Subject    : {subject}\n"
            f"Message-ID : {msg_id}\n"
            f"Preview    : {plain_text[:180]}...\n"
            f"========================================================================="
        )
        return {
            "success": True,
            "provider": "mock",
            "message_id": msg_id,
            "error": None
        }

    def _strip_html(self, html: str) -> str:
        """Helper to create basic plain text fallback from HTML."""
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# Singleton Instance
email_service = EmailService()


# -----------------------------------------------------------------------------
# Rich Responsive Email Templates
# -----------------------------------------------------------------------------

def get_base_email_template(title: str, preheader: str, body_html: str, action_button_html: str = "") -> str:
    """Base HTML Email layout with modern styling and responsive design."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; }}
    .container {{ max-width: 600px; margin: 20px auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
    .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }}
    .content {{ padding: 32px 24px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px 20px; margin: 20px 0; }}
    .card-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 14px; }}
    .card-row:last-child {{ margin-bottom: 0; }}
    .card-label {{ color: #64748b; font-weight: 600; }}
    .card-val {{ color: #0f172a; font-weight: 700; }}
    .btn {{ display: inline-block; background: #4f46e5; color: #ffffff !important; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; margin: 16px 0; }}
    .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div style="display:none;font-size:1px;color:#333333;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
    {preheader}
  </div>
  <div class="container">
    <div class="header">
      <h1>CareSync Healthcare</h1>
      <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">{title}</p>
    </div>
    <div class="content">
      {body_html}
      {f'<div style="text-align:center;">{action_button_html}</div>' if action_button_html else ''}
    </div>
    <div class="footer">
      <p style="margin:0 0 4px 0;">CareSync Medical Center &bull; Automated Notification System</p>
      <p style="margin:0;">Need assistance? Contact support@caresync-health.org</p>
    </div>
  </div>
</body>
</html>"""


def render_booking_confirmation_email(
    patient_name: str,
    doctor_name: str,
    specialization: str,
    appointment_date: str,
    start_time: str,
    appointment_id: int,
    is_doctor_copy: bool = False
) -> tuple[str, str, str]:
    """Generates (subject, html, text) for appointment booking confirmation."""
    if is_doctor_copy:
        subject = f"New Appointment Confirmed: {patient_name} ({appointment_date} at {start_time})"
        title = "New Consultation Scheduled"
        preheader = f"Patient {patient_name} has booked a consultation for {appointment_date}."
        body = f"""
        <p>Hello <strong>{doctor_name}</strong>,</p>
        <p>A new consultation has been confirmed and scheduled on your clinical calendar.</p>
        <div class="card">
          <div class="card-row"><span class="card-label">Patient Name:</span><span class="card-val">{patient_name}</span></div>
          <div class="card-row"><span class="card-label">Appointment ID:</span><span class="card-val">#{appointment_id}</span></div>
          <div class="card-row"><span class="card-label">Date:</span><span class="card-val">{appointment_date}</span></div>
          <div class="card-row"><span class="card-label">Time:</span><span class="card-val">{start_time}</span></div>
          <div class="card-row"><span class="card-label">Specialization:</span><span class="card-val">{specialization}</span></div>
        </div>
        <p>You can review the patient's pre-visit symptom analysis in your doctor portal.</p>
        """
        text = f"Hello {doctor_name},\nA new appointment with {patient_name} has been confirmed on {appointment_date} at {start_time} (ID: #{appointment_id})."
    else:
        subject = f"Appointment Confirmed: Dr. {doctor_name} on {appointment_date} at {start_time}"
        title = "Consultation Confirmed"
        preheader = f"Your appointment with Dr. {doctor_name} has been successfully confirmed."
        body = f"""
        <p>Hello <strong>{patient_name}</strong>,</p>
        <p>Your healthcare appointment has been successfully scheduled and confirmed.</p>
        <div class="card">
          <div class="card-row"><span class="card-label">Attending Physician:</span><span class="card-val">Dr. {doctor_name}</span></div>
          <div class="card-row"><span class="card-label">Department:</span><span class="card-val">{specialization}</span></div>
          <div class="card-row"><span class="card-label">Appointment ID:</span><span class="card-val">#{appointment_id}</span></div>
          <div class="card-row"><span class="card-label">Date:</span><span class="card-val">{appointment_date}</span></div>
          <div class="card-row"><span class="card-label">Time:</span><span class="card-val">{start_time}</span></div>
        </div>
        <p>Please arrive 10 minutes prior to your scheduled consultation time.</p>
        """
        text = f"Hello {patient_name},\nYour appointment with Dr. {doctor_name} ({specialization}) is confirmed for {appointment_date} at {start_time} (ID: #{appointment_id})."

    html = get_base_email_template(title, preheader, body)
    return subject, html, text


def render_cancellation_email(
    recipient_name: str,
    patient_name: str,
    doctor_name: str,
    appointment_date: str,
    start_time: str,
    appointment_id: int,
    reason: str,
    cancelled_by: str = "Patient"
) -> tuple[str, str, str]:
    """Generates (subject, html, text) for appointment cancellation."""
    subject = f"Appointment Cancelled: Consultation #{appointment_id} ({appointment_date})"
    title = "Appointment Cancelled"
    preheader = f"Notice: Consultation #{appointment_id} scheduled for {appointment_date} has been cancelled."
    body = f"""
    <p>Hello <strong>{recipient_name}</strong>,</p>
    <p>Please be advised that the following healthcare consultation has been cancelled:</p>
    <div class="card" style="border-left: 4px solid #ef4444;">
      <div class="card-row"><span class="card-label">Appointment ID:</span><span class="card-val">#{appointment_id}</span></div>
      <div class="card-row"><span class="card-label">Patient:</span><span class="card-val">{patient_name}</span></div>
      <div class="card-row"><span class="card-label">Physician:</span><span class="card-val">Dr. {doctor_name}</span></div>
      <div class="card-row"><span class="card-label">Scheduled Time:</span><span class="card-val">{appointment_date} at {start_time}</span></div>
      <div class="card-row"><span class="card-label">Cancelled By:</span><span class="card-val">{cancelled_by}</span></div>
      <div class="card-row"><span class="card-label">Reason:</span><span class="card-val">{reason or 'No reason specified'}</span></div>
    </div>
    <p>If you wish to book a new appointment, please visit the CareSync portal.</p>
    """
    text = f"Hello {recipient_name},\nAppointment #{appointment_id} with Dr. {doctor_name} on {appointment_date} at {start_time} has been cancelled by {cancelled_by}. Reason: {reason}."
    html = get_base_email_template(title, preheader, body)
    return subject, html, text


def render_reschedule_email(
    recipient_name: str,
    patient_name: str,
    doctor_name: str,
    old_date: str,
    old_time: str,
    new_date: str,
    new_time: str,
    appointment_id: int
) -> tuple[str, str, str]:
    """Generates (subject, html, text) for appointment reschedule."""
    subject = f"Appointment Rescheduled: Consultation #{appointment_id} (New Time: {new_date} {new_time})"
    title = "Appointment Rescheduled"
    preheader = f"Your consultation has been rescheduled to {new_date} at {new_time}."
    body = f"""
    <p>Hello <strong>{recipient_name}</strong>,</p>
    <p>Your appointment has been successfully rescheduled. Please review the updated consultation time below:</p>
    <div class="card" style="border-left: 4px solid #f59e0b;">
      <div class="card-row"><span class="card-label">Appointment ID:</span><span class="card-val">#{appointment_id}</span></div>
      <div class="card-row"><span class="card-label">Previous Slot:</span><span class="card-val" style="text-decoration:line-through;color:#94a3b8;">{old_date} at {old_time}</span></div>
      <div class="card-row"><span class="card-label">New Time:</span><span class="card-val" style="color:#059669;">{new_date} at {new_time}</span></div>
      <div class="card-row"><span class="card-label">Physician:</span><span class="card-val">Dr. {doctor_name}</span></div>
      <div class="card-row"><span class="card-label">Patient:</span><span class="card-val">{patient_name}</span></div>
    </div>
    """
    text = f"Hello {recipient_name},\nAppointment #{appointment_id} has been rescheduled from {old_date} {old_time} to {new_date} {new_time} with Dr. {doctor_name}."
    html = get_base_email_template(title, preheader, body)
    return subject, html, text


def render_leave_notification_email(
    patient_name: str,
    doctor_name: str,
    appointment_date: str,
    start_time: str,
    appointment_id: int,
    reason: str
) -> tuple[str, str, str]:
    subject = f"Appointment Update: Dr. {doctor_name} Unavailable on {appointment_date}"
    title = "Physician Unavailability Notice"
    preheader = f"Dr. {doctor_name} will be unavailable on {appointment_date}. Your appointment #{appointment_id} has been cancelled."
    body = f"""
    <p>Hello <strong>{patient_name}</strong>,</p>
    <p>We regret to inform you that <strong>Dr. {doctor_name}</strong> will be out of the clinic on <strong>{appointment_date}</strong> due to approved leave ({reason or 'Physician leave'}).</p>
    <div class="card" style="border-left: 4px solid #f97316;">
      <div class="card-row"><span class="card-label">Affected Appointment:</span><span class="card-val">#{appointment_id}</span></div>
      <div class="card-row"><span class="card-label">Originally Scheduled:</span><span class="card-val">{appointment_date} at {start_time}</span></div>
      <div class="card-row"><span class="card-label">Status:</span><span class="card-val" style="color:#dc2626;">CANCELLED (Doctor Leave)</span></div>
    </div>
    <p>We sincerely apologize for any inconvenience. Please log in to reschedule your consultation with Dr. {doctor_name} or choose another attending physician.</p>
    """
    text = f"Hello {patient_name},\nDr. {doctor_name} is unavailable on {appointment_date} ({reason}). Appointment #{appointment_id} at {start_time} has been cancelled. Please visit the portal to reschedule."
    html = get_base_email_template(title, preheader, body)
    return subject, html, text


def render_appointment_reminder_email(
    patient_name: str,
    doctor_name: str,
    specialization: str,
    appointment_date: str,
    start_time: str,
    appointment_id: int
) -> tuple[str, str, str]:
    """Generates (subject, html, text) for 24-hour upcoming appointment reminder."""
    subject = f"Reminder: Upcoming Appointment with Dr. {doctor_name} Tomorrow at {start_time}"
    title = "Consultation Reminder"
    preheader = f"Friendly reminder: your appointment with Dr. {doctor_name} is tomorrow at {start_time}."
    body = f"""
    <p>Hello <strong>{patient_name}</strong>,</p>
    <p>This is a friendly reminder of your upcoming consultation tomorrow:</p>
    <div class="card" style="border-left: 4px solid #3b82f6;">
      <div class="card-row"><span class="card-label">Physician:</span><span class="card-val">Dr. {doctor_name} ({specialization})</span></div>
      <div class="card-row"><span class="card-label">Appointment ID:</span><span class="card-val">#{appointment_id}</span></div>
      <div class="card-row"><span class="card-label">Date:</span><span class="card-val">{appointment_date}</span></div>
      <div class="card-row"><span class="card-label">Time:</span><span class="card-val">{start_time}</span></div>
    </div>
    <p>Please remember to bring any current prescriptions or medical history documents.</p>
    """
    text = f"Reminder for {patient_name}:\nUpcoming appointment with Dr. {doctor_name} on {appointment_date} at {start_time} (ID: #{appointment_id})."
    html = get_base_email_template(title, preheader, body)
    return subject, html, text


def render_medication_reminder_email(
    patient_name: str,
    medication_name: str,
    dosage: str,
    frequency: str,
    instructions: str,
    duration: str
) -> tuple[str, str, str]:
    """Generates (subject, html, text) for medication dosage reminder."""
    subject = f"Medication Reminder: Time to take {medication_name}"
    title = "Dosage Reminder"
    preheader = f"Reminder to take your prescribed dose of {medication_name} ({dosage})."
    body = f"""
    <p>Hello <strong>{patient_name}</strong>,</p>
    <p>It's time for your scheduled medication dose:</p>
    <div class="card" style="border-left: 4px solid #10b981;">
      <div class="card-row"><span class="card-label">Medication:</span><span class="card-val">{medication_name}</span></div>
      <div class="card-row"><span class="card-label">Dosage:</span><span class="card-val">{dosage}</span></div>
      <div class="card-row"><span class="card-label">Frequency:</span><span class="card-val">{frequency}</span></div>
      <div class="card-row"><span class="card-label">Instructions:</span><span class="card-val">{instructions or 'Take as prescribed'}</span></div>
      <div class="card-row"><span class="card-label">Prescription Duration:</span><span class="card-val">{duration}</span></div>
    </div>
    """
    text = f"Medication Reminder for {patient_name}:\nTime to take {medication_name} - Dosage: {dosage}, Frequency: {frequency}. Instructions: {instructions}."
    html = get_base_email_template(title, preheader, body)
    return subject, html, text
