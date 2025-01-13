Email customization Application

This project is a Flask-based web application designed to simplify email automation with features like CSV/Google Sheets upload, email customization, and scheduling. It integrates with Microsoft Graph, Google Sheets API, SendGrid API, and the Groq API for generating dynamic email content. The application also provides real-time analytics for email status and delivery metrics.

Features

User Authentication:

Microsoft OAuth2 login for secure access.

File Upload:

Upload CSV files containing recipient details (name, email, company).

Option to import data from Google Sheets.

Email Customization:

Customize subject and body with placeholders like {name}, {email}, etc.

Generate dynamic email content using Groq API.

Email Scheduling:

Schedule emails for specific times with delay functionality.

SendGrid Integration:

Send emails through SendGrid API.

Webhook support for real-time delivery and event tracking.

Analytics Dashboard:

Track email metrics (total sent, failed, scheduled, etc.).

Real-time updates via Server-Sent Events (SSE).

Prerequisites

Python 3.8+

Redis for Celery task management

API keys for:

Microsoft Graph

Google Sheets

SendGrid

Groq API
Usage

Login:

Click on the login button to authenticate via Microsoft.

Upload Data:

Upload a CSV file or import data from Google Sheets.

Customize Emails:

Customize email templates by filling in subject, body, and optional schedule time.

Track Analytics:

View email metrics in the analytics dashboard.

Monitor Updates:

Use the real-time updates section to track email statuses.
Technologies Used

Backend: Flask

Frontend: Jinja2 templates, HTML, CSS

Database: Redis (for task management)

APIs: Microsoft Graph, Google Sheets, SendGrid, Groq
