import os
import requests
import pandas as pd
from flask import Flask, render_template, redirect, request, session, flash, url_for, jsonify
from msal import ConfidentialClientApplication, PublicClientApplication
from werkzeug.utils import secure_filename
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from celery import Celery
import pytz
from datetime import datetime, timedelta
import json
from flask import Response
from flask import stream_with_context
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import time
from datetime import datetime
import threading
from time import sleep
from dotenv import load_dotenv
load_dotenv()



CLIENT_ID =  os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
AUTHORITY = 'https://login.microsoftonline.com/common'
SCOPE = ['Mail.Send', 'User.Read']
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SENDGRID_WEBHOOK_SECRET = os.getenv('SENDGRID_WEBHOOK_SECRET')
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
GROQ_API_KEY =  os.getenv('GROQ_API_KEY')

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


celery = Celery(__name__, broker='redis://localhost:6379')


email_metrics = {
    "total_sent": 0,
    "emails_pending": 0,
    "emails_scheduled": 0,
    "emails_failed": 0
}
email_statuses = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    auth_url = _build_auth_url()
    return redirect(auth_url)

def _build_auth_url():
    app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    return app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return 'Error: no code in response.'
    
    token = _get_token_from_code(code)
    session['access_token'] = token['access_token']
    return redirect(url_for('upload'))

def _get_token_from_code(code):
    app = ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
    result = app.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri=REDIRECT_URI)
    if "access_token" not in result:
        raise ValueError(f"Error acquiring token: {result.get('error_description', 'Unknown error')}")
    return result

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename.endswith('.csv'):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(file_path)
            emails = extract_data_from_csv(file_path)
            session['emails'] = emails
            return redirect(url_for('customize_email'))
        elif 'google_sheet' in request.form:
            return redirect(url_for('google_sheets'))
    
    return render_template('upload.html')

def extract_data_from_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        data = df[['name', 'email', 'company']].to_dict(orient='records')
        return data
    except Exception as e:
        print(f"Error extracting data: {e}")
        return []

@app.route('/google_sheets')
def google_sheets():
    creds = None
    if 'credentials' in session:
        creds = Credentials.from_authorized_user(session['credentials'])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)

        session['credentials'] = creds.to_json()

    service = build('sheets', 'v4', credentials=creds)
    SPREADSHEET_ID = 'your-google-sheet-id'
    RANGE_NAME = 'Sheet1!A:C'
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    data = [{"name": row[0], "email": row[1], "company": row[2]} for row in values[1:]]
    session['emails'] = data
    return redirect(url_for('customize_email'))




def replace_placeholders(email_data, body_template):
    
    for key, value in email_data.items():
        placeholder = f'{{{key}}}'  
        body_template = body_template.replace(placeholder, str(value))  
    return body_template




def generate_email_content(prompt, email_data):
    
    try:
        
        customized_prompt = prompt.format(**email_data) 

        
        GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
        

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

    
        payload = {
            "model": "gemma2-9b-it",  
            "messages": [{"role": "system", "content": "You are a helpful assistant."},
                         {"role": "user", "content": customized_prompt}]  
        }


        response = requests.post(GROQ_API_URL, json=payload, headers=headers)

    
        if response.status_code == 200:
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content
            else:
                return "Error: No content generated by the Groq API."
        else:
    
            error_message = response.json().get("error", "Groq API returned an error.")
            print(f"Groq API Error: {error_message} (status code: {response.status_code})")
            return f"Error: {error_message}"
    except Exception as e:
        print(f"Exception during API call: {e}")
        return "Error generating content due to an exception."


def schedule_email(email, subject, body, delay):

    def send_email_after_delay():
        print(f"Waiting for {delay} seconds to send the email to {email}.")
        sleep(delay)
        send_email(email, subject, body)

    thread = threading.Thread(target=send_email_after_delay)
    thread.start()

def send_email(email, subject, body):
    message = Mail(
        from_email='example_case@outlook.com',
        to_emails=email,
        subject=subject,
        html_content=body
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code == 202:
            print(f"Email sent successfully to {email}")
            email_metrics["total_sent"] += 1
        else:
            print(f"Failed to send email to {email}: {response.status_code}")
            email_metrics["emails_failed"] += 1
    except Exception as e:
        print(f"Error sending email to {email}: {e}")
        email_metrics["emails_failed"] += 1

@app.route('/customize', methods=['GET', 'POST'])
def customize_email():
    emails_data = session.get('emails', [])
     
    if request.method == 'POST':
        for idx, email_data in enumerate(emails_data):
            subject_template = request.form.get(f'subject_{idx}')
            body_template = request.form.get(f'body_{idx}')
            prompt_content = request.form.get(f'prompt_{idx}')  
            
            
            subject_template = subject_template.format(**email_data)
            body_template = replace_placeholders(email_data, body_template)
            
            
            generated_content = generate_email_content(prompt_content, email_data)  
            
            if isinstance(generated_content, str) and "Error" in generated_content:
                flash(generated_content, "error")
                continue
            
            
            body_template = generated_content

            schedule_time_str = request.form.get(f'schedule_time_{idx}')
            
            if schedule_time_str:
                try:
                    schedule_time = datetime.fromisoformat(schedule_time_str)
                except ValueError:
                    flash(f"Invalid datetime format for schedule time at index {idx + 1}: {schedule_time_str}", "error")
                    return redirect(url_for('customize_email'))
            else:
                schedule_time = datetime.now()
            access_token = session.get('access_token')
            if not access_token:
                flash("Session expired. Please log in again.") 
                return redirect(url_for('login'))
                
            delay = (schedule_time - datetime.now()).total_seconds()
            delay = max(0, delay)  

            
            schedule_email(email_data['email'], subject_template, body_template, delay)
        
        flash("Emails scheduled successfully!", "success")
        return redirect(url_for('index'))

    return render_template('customize.html', emails=emails_data)



@app.route('/sendgrid-webhook', methods=['POST'])
def sendgrid_webhook():
    webhook_payload = request.get_json()

    try:
    
        for event in webhook_payload:
            email_id = event.get("email")
            event_type = event.get("event")
            
            if email_id and event_type:
        
                if email_id not in email_statuses:
                    email_statuses[email_id] = {}

                
                email_statuses[email_id][event_type] = True  
                update_email_metrics(email_id, event_type)

        return jsonify({"message": "Webhook processed successfully"}), 200
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"error": "Failed to process webhook"}), 500



@app.route('/analytics', methods=['GET'])
def analytics():
    return {
        "metrics": {
            "total_sent": email_metrics["total_sent"],
            "emails_pending": email_metrics["emails_pending"],
            "emails_scheduled": email_metrics["emails_scheduled"],
            "emails_failed": email_metrics["emails_failed"]
        },
        "statuses": {email: {"events": statuses} for email, statuses in email_statuses.items()} 
    }


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')



email_metrics = {
    "total_sent": 0,
    "emails_pending": 0,
    "emails_scheduled": 0,
    "emails_failed": 0
}

email_statuses = {}

event_types = ['delivered', 'open', 'click', 'bounce'] 


def update_email_metrics(email_id, event_type):
    global email_metrics
    if email_id not in email_metrics:
        email_metrics[email_id] = {
            "delivered": False,
            "bounce": False,
            "open": False,
            "click": False
        }
        
    if email_statuses[email_id].get(event_type, False):
        print(f"Event '{event_type}' already processed for email {email_id}. Skipping.")
        return  

    
    email_metrics[email_id][event_type] = True

    
    if event_type == 'delivered':
        email_metrics["total_sent"] += 1  
    elif event_type == 'bounce':
        email_metrics["emails_failed"] += 1  
    elif event_type == 'open':
        pass 
    elif event_type == 'click':
        pass  

    print(f"Updated metrics for {email_id}: {email_metrics}")


@app.route('/sse')
def sse():
    def event_stream():
        while True:
            global email_metrics, email_statuses
            time.sleep(2)  
            data = {
                "metrics": {
                    "total_sent": email_metrics["total_sent"],
                    "emails_pending": email_metrics["emails_pending"],
                    "emails_scheduled": email_metrics["emails_scheduled"],
                    "emails_failed": email_metrics["emails_failed"],
                },
                "statuses": email_statuses
            }
            print(f"Sending data: {json.dumps(data)}")  
            yield f"data: {json.dumps(data)}\n\n"

    return Response(stream_with_context(event_stream()), content_type='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True)