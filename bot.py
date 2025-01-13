import imaplib
import smtplib
import email
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import json
import requests
import logging
from config import EMAIL_ACCOUNT, EMAIL_PASSWORD, IMAP_SERVER, SMTP_SERVER, MAILBOX, OLLAMA_MODEL_URL, OLLAMA_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Function to connect to the email server
def connect_email_server():
    try:
        logging.info("Connecting to the email server...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select(MAILBOX)
        logging.info("Connected successfully.")
        return mail
    except Exception as e:
        logging.error(f"Failed to connect to the email server: {e}")
        return None

# Function to fetch unread emails
def fetch_unread_emails(mail):
    logging.info("Searching for unread emails...")
    status, response = mail.search(None, 'UNSEEN')
    if status != "OK":
        logging.error("No new emails found.")
        return []

    email_ids = response[0].split()
    if not email_ids:
        logging.info("No new emails to process.")
        return []

    emails = []
    for email_id in email_ids:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            logging.error(f"Failed to fetch email with ID: {email_id}")
            continue
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                emails.append(msg)
    return emails

# Function to get email body
def get_email_body(msg):
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode()
    return ""

# Function to query Ollama's Llama model (or any other locally hosted model)
def query_llama_model(question):
    try:
        logging.info("Querying the Llama model...")

        # Construct the request payload
        payload = {
            "model": "llama3.2:latest",  # Specify the model name
            "prompt": question            # The query sent to the model
        }

        # Sending the POST request to the local Ollama server with stream=True
        response = requests.post("http://localhost:11434/api/generate", json=payload, stream=True)
        response.raise_for_status()  # Will raise an exception for 4xx/5xx errors

        # Initialize a list to collect response parts
        response_text = ""

        # Check if the response is a valid stream
        if response.status_code == 200:
            for chunk in response.iter_lines():
                if chunk:
                    try:
                        # Decode the chunk to a string
                        decoded_chunk = chunk.decode('utf-8')

                        # Try to parse the JSON chunk
                        json_chunk = json.loads(decoded_chunk)

                        # If "done" is True, that means the model has finished responding
                        if json_chunk.get("done", False):
                            break

                        # Append the response part to the full response text
                        response_text += json_chunk.get("response", "")

                    except json.JSONDecodeError as e:
                        # Handle any JSON decoding issues
                        logging.warning(f"Skipping malformed chunk: {decoded_chunk} - {e}")
                        continue

        else:
            logging.error(f"Received unexpected status code: {response.status_code}")
            return "Error: Unexpected server response."

        # Simplified HTML response
        html_response = """
        <html>
            <body>
                <p><strong>Original Question:</strong><br>{}</p>
                <p><strong>Response:</strong><br>{}</p>
            </body>
        </html>
        """.format(question, response_text)  # Include both the original query and response

        # Return the HTML-formatted response
        return html_response.strip()

    except requests.exceptions.RequestException as e:
        logging.error(f"Error querying the Llama model: {e}")
        return "Sorry, there was an issue generating a response."
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return "An unexpected error occurred."



# Function to send a reply email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

def send_reply_email(subject, body, to_email, message_id):
    try:
        logging.info(f"Sending reply to {to_email}...")

        # Create the message container
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ACCOUNT
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['In-Reply-To'] = message_id
        msg['References'] = message_id

        # Attach the HTML content (make sure this is 'html')
        msg.attach(MIMEText(body, 'html'))  # Correct MIME type for HTML

        # Send the email
        with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, to_email, msg.as_string())

        logging.info(f"Reply sent to {to_email}.")
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {e}")



# Main process loop
def main():
    while True:
        mail = connect_email_server()
        if mail is None:
            logging.error("Could not connect to email server. Exiting...")
            break

        emails = fetch_unread_emails(mail)
        if not emails:
            logging.info("No new emails. Sleeping for 7 seconds...")
            time.sleep(7)
            continue

        for msg in emails:
            subject = msg["subject"]
            sender = msg["from"]
            body = get_email_body(msg)

            logging.info(f"New email received!")
            logging.info(f"Subject: {subject}")
            logging.info(f"From: {sender}")
            logging.info(f"Body: {body}")

            # Query Llama model for the response in HTML format, including the original query
            response = query_llama_model(body)

            # Send the response as a reply (in HTML format)
            send_reply_email(subject, response, sender, msg["Message-ID"])

        logging.info("Sleeping for 7 seconds before checking for new emails...")
        time.sleep(7)

if __name__ == "__main__":
    main()
