import sounddevice as sd
from scipy.io.wavfile import write
from resemblyzer import preprocess_wav, VoiceEncoder
from pathlib import Path
import numpy as np
from flask import Blueprint, jsonify, request
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

voice_bp = Blueprint('voice', __name__)

# --- SETTINGS ---
duration = 3  # Duration for recording in seconds
fs = 16000  # Sampling rate
THRESHOLD = 0.55  # Lowered threshold for better recognition

# Initialize encoder globally
encoder = VoiceEncoder()

# --- KNOWN SPEAKER DIRECT PATHS ---
speaker_paths = {
    "1MJ21AI002": Path(r"C:\Users\Sushmitha\OneDrive\Desktop\MNS\static\voice_samples\1MJ21AI002"),
    "1MJ21AI030": Path(r"C:\Users\Sushmitha\OneDrive\Desktop\MNS\static\voice_samples\1MJ21AI030"),
    "1MJ21AI034": Path(r"C:\Users\Sushmitha\OneDrive\Desktop\MNS\static\voice_samples\1MJ21AI034"),
    "1MJ21AI052": Path(r"C:\Users\Sushmitha\OneDrive\Desktop\MNS\static\voice_samples\1MJ21AI052"),
}

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_speaker_embeddings(usn):
    embeddings = []
    folder_path = speaker_paths.get(usn)
    if not folder_path:
        return None
    
    for wav_file in folder_path.glob("voice_*.wav"):
        try:
            wav = preprocess_wav(wav_file)
            emb = encoder.embed_utterance(wav)
            embeddings.append(emb)
        except Exception as e:
            print(f"Error processing {wav_file.name} for {usn}: {e}")
    return embeddings if embeddings else None

@voice_bp.route('/verify', methods=['POST'])
def verify_voice():
    try:
        data = request.get_json()
        usn = data.get('usn')
        
        if not usn:
            return jsonify({'success': False, 'message': 'No USN provided'})

        # Record voice with improved settings
        temp_test_file = Path("live_test.wav")
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
        sd.wait()
        # Normalize the recording
        recording = np.int16(recording * 32767)
        write(temp_test_file, fs, recording)

        # Load known speaker embeddings
        known_embeddings = load_speaker_embeddings(usn)
        if not known_embeddings:
            return jsonify({'success': False, 'message': 'No voice samples found for this USN'})

        # Process recorded voice
        try:
            test_wav = preprocess_wav(temp_test_file)
            test_embedding = encoder.embed_utterance(test_wav)
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error processing recorded voice: {str(e)}'})

        # Compare with known samples
        total_score = 0
        for emb in known_embeddings:
            score = cosine_similarity(emb, test_embedding)
            total_score += score
        avg_score = total_score / len(known_embeddings)

        # Make decision
        if avg_score >= THRESHOLD:
            return jsonify({
                'success': True,
                'message': f'Voice verified (Score: {avg_score:.4f})',
                'score': float(avg_score)
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Voice verification failed (Score: {avg_score:.4f} < {THRESHOLD})',
                'score': float(avg_score)
            })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

    finally:
        # Cleanup
        if os.path.exists("live_test.wav"):
            try:
                os.remove("live_test.wav")
            except:
                pass

# Add these at the top with other global variables
OTP_CACHE = {}  # {usn: {'otp': '123456', 'expiry': datetime}}

# Update the email settings
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # Changed to SSL port
SENDER_EMAIL = "sushmithahk.hirenallur@gmail.com"
SENDER_PASSWORD = "sewt rvtd ygyd uixd"

# Add after the OTP_CACHE definition and before the email settings
def get_student_email(usn):
    # Student email mapping
    student_emails = {
        "1MJ21AI002": "afrafalakh16@gmail.com",
        "1MJ21AI030": "madhuribolla3734@gmail.com",
        "1MJ21AI034": "nithyapvnk@gmail.com",
        "1MJ21AI052": "sushmithahk27@gmail.com"
    }
    return student_emails.get(usn)

def generate_and_send_otp(usn, email):
    try:
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        expiry = datetime.now() + timedelta(minutes=5)
        
        message = MIMEMultipart()
        message["From"] = SENDER_EMAIL
        message["To"] = email
        message["Subject"] = "Attendance Verification OTP"
        
        body = f"""
        Dear Student,
        
        Your OTP for attendance verification is: {otp}
        This OTP will expire in 5 minutes.
        
        If you didn't request this OTP, please ignore this email.
        
        Best regards,
        MVJ College Of Engineering
        """
        
        message.attach(MIMEText(body, "plain"))
        
        # Using SSL instead of TLS
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(message)
        
        OTP_CACHE[usn] = {'otp': otp, 'expiry': expiry}
        print(f"OTP sent successfully to {email}")  # Debug log
        return True
        
    except Exception as e:
        print(f"Detailed error in sending OTP: {str(e)}")  # Debug log
        return False

@voice_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        usn = data.get('usn')
        submitted_otp = data.get('otp')
        
        print(f"Verifying OTP - USN: {usn}, Submitted OTP: {submitted_otp}")  # Debug log
        print(f"OTP Cache: {OTP_CACHE}")  # Debug log
        
        if not usn:
            return jsonify({'success': False, 'message': 'USN required'})
        
        # If otp is "send", generate and send new OTP
        if submitted_otp == "send":
            student_email = get_student_email(usn)
            if not student_email:
                return jsonify({'success': False, 'message': 'Student email not found'})
                
            if generate_and_send_otp(usn, student_email):
                return jsonify({'success': True, 'message': 'OTP sent successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to send OTP. Please try again.'})
        
        # Regular OTP verification
        if not submitted_otp:
            return jsonify({'success': False, 'message': 'OTP required'})
        
        otp_data = OTP_CACHE.get(usn)
        if not otp_data:
            return jsonify({'success': False, 'message': 'No OTP found or expired'})
        
        if datetime.now() > otp_data['expiry']:
            del OTP_CACHE[usn]
            return jsonify({'success': False, 'message': 'OTP expired'})
        
        print(f"Comparing OTPs - Submitted: {submitted_otp}, Stored: {otp_data['otp']}")  # Debug log
        
        if submitted_otp == otp_data['otp']:
            del OTP_CACHE[usn]
            return jsonify({'success': True, 'message': 'OTP verified successfully'})
        
        return jsonify({'success': False, 'message': 'Invalid OTP'})
        
    except Exception as e:
        print(f"Error in verify_otp: {str(e)}")
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})