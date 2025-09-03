from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import os
import logging
import cv2
import face_recognition
import numpy as np
import base64
import dlib
from io import BytesIO
from pathlib import Path
import requests
import re
import shutil
from urllib.parse import urlparse
import bz2
from Model.take_attendance import attendance_bp, init_face_recognition
from Model.voice_recognition import voice_bp
from random import randint
from flask_mail import Mail, Message

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
STUDENT_IMAGES_DIR = os.path.join(STATIC_DIR, 'student_images')
MODEL_DIR = os.path.join(BASE_DIR, 'Model')

# Global variables for recording
recording_timer = None
camera_instance = None
recording_active = False

# Create necessary directories
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(STUDENT_IMAGES_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# Initialize Flask app
# After app initialization and before routes (around line 40)
app = Flask(__name__)
app.secret_key = 'mvj_attendance_system_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add mail configuration here
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465  # Changed to SSL port
app.config['MAIL_USE_TLS'] = False  # Changed to False since we're using SSL
app.config['MAIL_USE_SSL'] = True   # Added SSL configuration
app.config['MAIL_USERNAME'] = 'sushmithahk.hirenallur@gmail.com'
app.config['MAIL_PASSWORD'] = 'sewt rvtd ygyd uixd'
mail = Mail(app)

# Initialize extensions
CORS(app, resources={r"/*": {"origins": "*"}})
db = SQLAlchemy(app)

# Add OTP helper functions here
def generate_otp():
    return str(randint(100000, 999999))

def send_otp_email(email, otp):
    try:
        msg = Message(
            'Attendance System OTP',
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f'Your OTP for attendance verification is: {otp}'
        mail.send(msg)
        return True
    except Exception as e:
        logger.error(f"Email send error: {str(e)}")
        return False

# Register the attendance blueprint
app.register_blueprint(attendance_bp, url_prefix='/attendance')

# Register the voice blueprint
app.register_blueprint(voice_bp, url_prefix='/voice')

# Database Models
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    usn = db.Column(db.String(20), unique=True, nullable=False)
    branch = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    image_url = db.Column(db.String(500))
    voice_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    verification_method = db.Column(db.String(50))
    student = db.relationship('Student', backref='attendances')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    branch = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(1), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

def download_google_drive_image(url, usn):
    try:
        logger.info(f"Processing image for {usn}")
        local_path = os.path.join('student_images', f'{usn}.jpg')
        full_path = os.path.join(STUDENT_IMAGES_DIR, f'{usn}.jpg')

        if os.path.exists(full_path):
            logger.info(f"Using existing image for {usn}")
            return local_path

        if not url.startswith(('http://', 'https://')):
            if os.path.exists(url):
                shutil.copy2(url, full_path)
                return local_path
            logger.error(f"Local file not found: {url}")
            return None

        if 'drive.google.com' in url:
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()

                with open(full_path, 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                
                img = cv2.imread(full_path)
                if img is not None:
                    logger.info(f"Successfully downloaded image to {full_path}")
                    return local_path
                else:
                    os.remove(full_path)
                    logger.error(f"Invalid image file for {usn}")
                    return None

            except Exception as e:
                logger.error(f"Drive download error for {usn}: {str(e)}")
                if os.path.exists(full_path):
                    os.remove(full_path)
                return None

        return None
    except Exception as e:
        logger.error(f"Error downloading image for {usn}: {str(e)}")
        return None

# Routes
@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            if username == "MVJ" and password == "MVJ@25":
                session['logged_in'] = True
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid credentials!', 'error')
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        flash('An error occurred during login', 'error')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/upload_students', methods=['GET', 'POST'])
def upload_students():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    branches = {
        'AIML': ['A'],
        'CSE': ['A', 'B', 'C', 'D'],
        'ECE': ['A', 'B', 'C'],
        'ISE': ['A', 'B']
    }
    semesters = list(range(1, 9))
    
    if request.method == 'POST':
        selected_branch = request.form.get('branch')
        selected_section = request.form.get('section')
        selected_semester = request.form.get('semester')
        
        if not all([selected_branch, selected_section, selected_semester]):
            return jsonify({'success': False, 'message': 'Please select all fields'})
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file selected'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if file and file.filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(file)
                required_columns = ['Name', 'USN', 'Branch', 'Semester', 
                                 'Email ID', 'Phone number', 'Image', 'Voice record']
                
                df.columns = df.columns.str.strip()
                
                if not all(col in df.columns for col in required_columns):
                    return jsonify({'success': False, 'message': 'Excel file missing required columns'})
                
                # Delete existing records if any
                Student.query.filter_by(
                    branch=selected_branch,
                    section=selected_section,
                    semester=selected_semester
                ).delete()
                
                UploadedFile.query.filter_by(
                    branch=selected_branch,
                    section=selected_section,
                    semester=selected_semester
                ).delete()
                
                # Add new records
                for _, row in df.iterrows():
                    student = Student(
                        name=row['Name'],
                        usn=row['USN'],
                        branch=selected_branch,
                        section=selected_section,
                        semester=selected_semester,
                        email=row['Email ID'],
                        phone=str(row['Phone number']),
                        image_url=row['Image'],
                        voice_url=row['Voice record']
                    )
                    db.session.add(student)
                
                # Record the upload
                upload_record = UploadedFile(
                    branch=selected_branch,
                    section=selected_section,
                    semester=selected_semester
                )
                db.session.add(upload_record)
                
                db.session.commit()
                return jsonify({'success': True, 'message': 'Students data uploaded successfully!'})
            except Exception as e:
                db.session.rollback()
                return jsonify({'success': False, 'message': f'Error processing file: {str(e)}'})
        else:
            return jsonify({'success': False, 'message': 'Please upload an Excel file'})
    
    return render_template('upload_students.html', 
                         branches=branches, 
                         semesters=semesters)


@app.route('/view_students')
def view_students():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    branches = {
        'AIML': ['A'],
        'CSE': ['A'],
        'ECE': ['A'],
        'ISE': ['A']
    }
    semesters = list(range(1, 9))
    
    return render_template('view_students.html',
                         branches=branches,
                         semesters=semesters)

@app.route('/get_sections/<branch>')
def get_sections(branch):
    branches = {
        'AIML': ['A'],
        'CSE': ['A'],
        'ECE': ['A'],
        'ISE': ['A']
    }
    return jsonify(sections=branches.get(branch, []))

@app.route('/get_semesters')
def get_semesters():
    semesters = list(range(1, 9))
    return jsonify({'semesters': semesters})

@app.route('/check_upload_status')
def check_upload_status():
    branch = request.args.get('branch')
    section = request.args.get('section')
    semester = request.args.get('semester')
    
    if not all([branch, section, semester]):
        return jsonify({'exists': False})
    
    exists = UploadedFile.query.filter_by(
        branch=branch,
        section=section,
        semester=semester
    ).first() is not None
    
    return jsonify({'exists': exists})

@app.route('/get_students')
def get_students():
    branch = request.args.get('branch')
    section = request.args.get('section')
    semester = request.args.get('semester')
    
    query = Student.query
    if branch:
        query = query.filter_by(branch=branch)
    if section:
        query = query.filter_by(section=section)
    if semester:
        query = query.filter_by(semester=semester)
    
    students = query.all()
    student_list = []
    for student in students:
        student_list.append({
            'name': student.name,
            'usn': student.usn,
            'branch': student.branch,
            'section': student.section,
            'semester': student.semester,
            'email': student.email,
            'phone': student.phone,
            'image_url': student.image_url,
            'voice_url': student.voice_url
        })
    
    return jsonify({'success': True, 'students': student_list})

@app.route('/delete_file', methods=['POST'])
def delete_file():
    if not session.get('logged_in'):
        return jsonify({'success': False})
    
    try:
        branch = request.form.get('branch')
        section = request.form.get('section')
        semester = request.form.get('semester')
        
        Student.query.filter_by(
            branch=branch,
            section=section,
            semester=semester
        ).delete()
        
        UploadedFile.query.filter_by(
            branch=branch,
            section=section,
            semester=semester
        ).delete()
        
        db.session.commit()
        
        # Reinitialize face recognition after deleting students
        if init_face_recognition():
            logger.info("Face recognition reinitialized after deleting students")
        else:
            logger.error("Failed to reinitialize face recognition")
            
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/attendance_details')
def attendance_details():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    branches = {
        'AIML': ['A'],
        'CSE': ['A'],
        'ECE': ['A'],
        'ISE': ['A']
    }
    semesters = list(range(1, 9))
    
    return render_template('attendance_details.html',
                         branches=branches,
                         semesters=semesters)
                         
@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    try:
        data = request.get_json()
        usn = data.get('usn')
        verification_method = data.get('verification_method', '')

        if not usn:
            return jsonify({'success': False, 'message': 'No USN provided'}), 400

        student = Student.query.filter_by(usn=usn).first()
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'}), 404

        today = datetime.now().date()
        existing = Attendance.query.filter_by(student_id=student.id, date=today).first()
        
        # Clean up verification method
        current_methods = set(verification_method.split(' + ')) if verification_method else set()
        current_methods.discard('')
        current_methods.discard('null')
        
        if existing:
            # Update existing attendance record
            existing_methods = set(existing.verification_method.split(' + ')) if existing.verification_method else set()
            existing_methods.discard('')
            existing_methods.discard('null')
            
            # Combine all verification methods
            all_methods = existing_methods.union(current_methods)
            existing.verification_method = ' + '.join(sorted(all_methods))
            db.session.commit()
            return jsonify({'success': True, 'message': 'Verification method updated'})

        # Create new attendance record
        attendance = Attendance(
            student_id=student.id,
            date=today,
            time=datetime.now().time(),
            verification_method=' + '.join(sorted(current_methods))
        )
        db.session.add(attendance)
        db.session.commit()

        return jsonify({'success': True, 'message': '✅ Attendance marked successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
@app.route('/help')
def help():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('help.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/get_attendance')
def get_attendance():
    branch = request.args.get('branch')
    section = request.args.get('section')
    semester = request.args.get('semester')
    date = request.args.get('date')
    
    try:
        attendance_date = datetime.strptime(date, '%Y-%m-%d').date() if date else datetime.now().date()
        
        # Get all students in the selected branch/section/semester
        student_query = Student.query
        if branch:
            student_query = student_query.filter_by(branch=branch)
        if section:
            student_query = student_query.filter_by(section=section)
        if semester:
            student_query = student_query.filter_by(semester=semester)
        
        students = student_query.all()
        attendance_list = []
        
        for student in students:
            # Check attendance for this student on the selected date
            attendance = Attendance.query.filter_by(
                student_id=student.id,
                date=attendance_date
            ).first()
            
            if attendance:
                attendance_list.append({
                    'usn': student.usn,
                    'name': student.name,
                    'time': attendance.time.strftime('%I:%M %p'),
                    'verification_method': attendance.verification_method,
                    'status': 'Present'
                })
            else:
                attendance_list.append({
                    'usn': student.usn,
                    'name': student.name,
                    'time': '-',
                    'verification_method': '-',
                    'status': 'Absent'
                })
        
        return jsonify({
            'success': True,
            'attendance': attendance_list
        })
        
    except Exception as e:
        logger.error(f"Error getting attendance: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'attendance': []
        })

@app.route('/export_attendance')
def export_attendance():
    branch = request.args.get('branch')
    section = request.args.get('section')
    semester = request.args.get('semester')
    date = request.args.get('date')
    format = request.args.get('format', 'csv')
    
    try:
        attendance_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        attendance_records = db.session.query(
            Student.usn, 
            Student.name, 
            Attendance.time,
            Attendance.verification_method  # Add this line
        ).join(
            Attendance
        ).filter(
            Student.branch == branch,
            Student.section == section,
            Student.semester == semester,
            Attendance.date == attendance_date
        ).all()
        
        df = pd.DataFrame(attendance_records, columns=['USN', 'Name', 'Time', 'Verification Method'])  # Updated columns
        df['Time'] = df['Time'].apply(lambda x: x.strftime('%I:%M %p'))
        
        if format == 'csv':
            output = BytesIO()
            df.to_csv(output, index=False)
            output.seek(0)
            return send_file(
                output,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'attendance_{branch}_{section}_{semester}_{date}.csv'
            )
        else:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'attendance_{branch}_{section}_{semester}_{date}.xlsx'
            )
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
        
if __name__ == "__main__":
    try:
        logger.info("Initializing application...")
        with app.app_context():
            db.create_all()
            if init_face_recognition():
                logger.info("Face recognition initialized")

                # ✅ ADD THIS LINE
                from Model import take_attendance
                logger.info(f"✅ Faces loaded: {list(take_attendance.known_faces.keys())}")
            else:
                logger.error("Face recognition failed to initialize")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Error starting application: {e}")