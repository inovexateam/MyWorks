"""
Email reporting - sends sprint burndown + churn charts as an HTML email
with embedded images, via SMTP.
"""
import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime


def send_sprint_report_email(chart_paths: dict, summary_html: str, sprint_name: str,
                               smtp_host=None, smtp_port=None, smtp_user=None, smtp_pass=None,
                               email_from=None, email_to=None):
    """
    chart_paths: dict like {"burndown": "/path/burndown.png", "churn": "/path/churn.png", ...}
    summary_html: pre-rendered HTML table/snippet for the summary section
    """
    smtp_host = smtp_host or os.environ.get("SMTP_HOST")
    smtp_port = int(smtp_port or os.environ.get("SMTP_PORT", 587))
    smtp_user = smtp_user or os.environ.get("SMTP_USER")
    smtp_pass = smtp_pass or os.environ.get("SMTP_PASS")
    email_from = email_from or os.environ.get("EMAIL_FROM", smtp_user)
    email_to = email_to or os.environ.get("EMAIL_TO", "")

    if not all([smtp_host, smtp_user, smtp_pass, email_to]):
        raise ValueError("SMTP configuration incomplete. Check SMTP_HOST/USER/PASS and EMAIL_TO.")

    recipients = [e.strip() for e in email_to.split(",") if e.strip()]

    msg = EmailMessage()
    msg["Subject"] = f"Sprint Report: {sprint_name} — {datetime.now().strftime('%Y-%m-%d')}"
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)

    cid_map = {name: make_msgid(domain="sprintdash.local") for name in chart_paths}

    html_imgs = "".join(
        f'<h3 style="font-family:Arial,sans-serif;color:#222;">{label}</h3>'
        f'<img src="cid:{cid_map[label][1:-1]}" style="max-width:100%;border:1px solid #ddd;border-radius:6px;margin-bottom:20px;"/>'
        for label in chart_paths
    )

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#222;">
      <h2>Sprint Report — {sprint_name}</h2>
      <p>Generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
      {summary_html}
      {html_imgs}
      <p style="color:#888;font-size:12px;">Sent by JIRA Sprint Dashboard</p>
    </body></html>
    """

    msg.set_content("This email contains an HTML sprint report. Please view in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    # attach images with matching CIDs
    for label, path in chart_paths.items():
        with open(path, "rb") as f:
            img_data = f.read()
        msg.get_payload()[1].add_related(img_data, maintype="image", subtype="png", cid=cid_map[label])

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
