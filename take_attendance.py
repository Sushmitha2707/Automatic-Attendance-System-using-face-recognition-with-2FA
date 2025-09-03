import cv2
import numpy as np
import os
import logging
from flask import Flask, Response, render_template, jsonify, request
from datetime import datetime, timezone
import dlib
from threading import Timer
import time
from flask_cors import CORS
from flask import Blueprint
import atexit 
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from Model.voice_recognition import voice_bp

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
known_faces = {}
known_names = {}
student_map = {}  # Map student IDs to names
attendance_recorded = set()
attendance_times = {}
recording_active = False
recording_timer = None
camera_instance = None
face_buffer = {}  # For tracking faces across frames

# Initialize dlib's face detector and face recognition model
face_detector = dlib.get_frontal_face_detector()
shape_predictor = dlib.shape_predictor(os.path.join(os.path.dirname(__file__), "shape_predictor_68_face_landmarks.dat"))
face_rec_model = dlib.face_recognition_model_v1(os.path.join(os.path.dirname(__file__), "dlib_face_recognition_resnet_model_v1.dat"))

student_map = {
    "1MJ21AI002": "1MJ21AI002",
    "1MJ21AI030": "1MJ21AI030",
    "1MJ21AI034": "1MJ21AI034",
    "1MJ21AI052": "1MJ21AI052"
}

def get_face_encoding(image):
    faces = face_detector(image)
    if len(faces) > 0:
        shape = shape_predictor(image, faces[0])
        face_encoding = np.array(face_rec_model.compute_face_descriptor(image, shape))
        return face_encoding
    return None

def load_student_faces():
    global known_faces, known_names
    base_dir = os.path.dirname(os.path.dirname(__file__))
    students_dir = os.path.join(base_dir, 'static', 'student_images')
    
    logger.info(f"Starting to load student faces from: {students_dir}")
    
    for student_id in student_map:
        logger.debug(f"Processing student: {student_id}")
        image_path = os.path.join(students_dir, student_id, 'front.jpg')
        
        if os.path.exists(image_path):
            try:
                image = cv2.imread(image_path)
                if image is None:
                    continue
                    
                # Convert BGR to RGB
                rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                face_encoding = get_face_encoding(rgb_image)
                if face_encoding is not None:
                    known_faces[student_id] = face_encoding
                    known_names[student_id] = student_map[student_id]
                    logger.info(f"Successfully loaded face for {student_id}")
                    
            except Exception as e:
                logger.error(f"Error processing {image_path}: {str(e)}")

# Add these to your global variables
face_buffer = {}
BUFFER_SIZE = 10
REQUIRED_CONSISTENT_FRAMES = 5

# Add these with your other global variables
voice_verified = set()
otp_verified = set()


# Add after student_map definition and before get_face_encoding function
def init_face_recognition():
    """Initialize face recognition by loading student faces"""
    global known_faces, known_names
    try:
        logger.info("Initializing face recognition...")
        load_student_faces()
        if len(known_faces) == 0:
            logger.warning("No face encodings loaded!")
            return False
        logger.info(f"Successfully loaded {len(known_faces)} face encodings")
        return True
    except Exception as e:
        logger.error(f"Error initializing face recognition: {e}")
        return False

# Update generate_frames function
# Modify the generate_frames function to better handle camera resources
# Fix the camera variable issue in generate_frames function
def generate_frames():
    global camera_instance
    
    # Add error frame generation
    def create_error_frame(message):
        error_img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(error_img, message, 
                  (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        ret, buffer = cv2.imencode('.jpg', error_img)
        return buffer.tobytes()

    # Try to initialize camera
    if camera_instance is None:
        try:
            camera_instance = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Try DirectShow
            if not camera_instance.isOpened():
                camera_instance = cv2.VideoCapture(0)  # Try default
        except Exception as e:
            logger.error(f"Camera initialization error: {str(e)}")
            error_frame = create_error_frame("Camera Error - Cannot access webcam")
            yield (b'--frame\r\n'
                  b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
            return

    while True:
        try:
            if not camera_instance.isOpened():
                error_frame = create_error_frame("Camera disconnected")
                yield (b'--frame\r\n'
                      b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
                camera_instance = cv2.VideoCapture(0)
                continue

            success, frame = camera_instance.read()
            if not success:
                error_frame = create_error_frame("Failed to capture frame")
                yield (b'--frame\r\n'
                      b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
                continue

            if not recording_active:
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank_frame, "Click Start Recording", (180, 240),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                ret, buffer = cv2.imencode('.jpg', blank_frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                time.sleep(0.1)  # Add small delay to reduce CPU usage
                continue

            # Fix: Use camera_instance instead of cap
            ret, frame = camera_instance.read()
            if not ret:
                logger.error("Failed to read frame from camera")
                time.sleep(0.5)
                continue

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = face_detector(rgb_frame)
            
            for face in faces:
                shape = shape_predictor(rgb_frame, face)
                face_encoding = np.array(face_rec_model.compute_face_descriptor(rgb_frame, shape))
                
                # Compare with known faces
                distances = []
                for student_id, known_encoding in known_faces.items():
                    distance = np.linalg.norm(face_encoding - known_encoding)
                    distances.append((student_id, distance))
                
                # Sort distances to find best and second best matches
                distances.sort(key=lambda x: x[1])
                
                if len(distances) >= 2:
                    best_match = distances[0]
                    second_best = distances[1]
                    
                    # Calculate ratio between best and second best match
                    ratio = best_match[1] / second_best[1]
                    
                    # Check if face matches any known student
                    if best_match[1] < 0.5:  # Distance threshold
                        student_id = best_match[0]
                        name = student_map[student_id]
                        
                        # Enhanced confidence calculation
                        raw_confidence = 1 - best_match[1]
                        confidence = max(0, min(100, raw_confidence * 150))
                        
                        if confidence > 65:  # Confidence threshold
                            left = face.left()
                            top = face.top()
                            right = face.right()
                            bottom = face.bottom()
                            
                            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                            cv2.putText(frame, f"{name} ({confidence:.1f}%)", (left, top - 10),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
                            
                            if student_id not in attendance_recorded:
                                attendance_recorded.add(student_id)
                                attendance_times[student_id] = datetime.now().strftime('%H:%M:%S')
                                logger.info(f"New attendance recorded: {student_id} with confidence {confidence:.1f}%")
                    else:
                        # Unknown face
                        cv2.rectangle(frame, (face.left(), face.top()), (face.right(), face.bottom()), (0, 0, 255), 2)
                        cv2.putText(frame, "Unknown", (face.left(), face.top() - 10),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                else:
                    # No matches found
                    cv2.rectangle(frame, (face.left(), face.top()), (face.right(), face.bottom()), (0, 0, 255), 2)
                    cv2.putText(frame, "Unknown", (face.left(), face.top() - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                
            # Clean up old faces from buffer
            for loc in list(face_buffer.keys()):
                face_buffer[loc]['last_seen'] += 1
                if face_buffer[loc]['last_seen'] > 30:  # Remove after 30 frames
                    del face_buffer[loc]

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                   
        except Exception as e:
            logger.error(f"Error processing frame: {str(e)}")
            continue


attendance_bp = Blueprint('attendance', __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))

@attendance_bp.route('/cleanup', methods=['POST'])
def cleanup():
    global camera_instance, recording_active
    try:
        recording_active = False
        if camera_instance is not None:
            camera_instance.release()
            camera_instance = None
        cv2.destroyAllWindows()
        return jsonify({"status": "success", "message": "Camera cleaned up"})
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@atexit.register
def cleanup_camera():
    global camera_instance
    if camera_instance is not None:
        camera_instance.release()
        camera_instance = None
    cv2.destroyAllWindows()
    logger.info("Camera resources cleaned up")

# Remove the duplicate shutdown function since we already have cleanup_camera
@attendance_bp.route('/')
def take_attendance():
    return render_template('take_attendance.html')
@attendance_bp.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@attendance_bp.route('/get_attendance')
def get_attendance():
    attendance_list = []
    for student_id in attendance_recorded:
        verification_methods = []
        if student_id in attendance_recorded:
            verification_methods.append("Face")
        if student_id in voice_verified:
            verification_methods.append("Voice")
        if student_id in otp_verified:
            verification_methods.append("OTP")
            
        verification_string = " + ".join(filter(None, verification_methods)) if verification_methods else "-"
        
        attendance_list.append({
            'usn': student_id,
            'name': student_map.get(student_id, student_id),
            'time': attendance_times.get(student_id, '-'),
            'verification_method': verification_string,
            'status': 'Present'
        })
    return jsonify({'success': True, 'attendance': attendance_list})

@attendance_bp.route('/start_recording', methods=['POST'])
def start_recording():
    global recording_active, recording_timer
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()

        if not data:
            logger.error("No data received")
            return jsonify({"status": "error", "message": "No data received"}), 400
            
        branch = data.get('branch', '')
        section = data.get('section', '')
        semester = data.get('semester', '')
        
        # Make parameters optional
        # Reset attendance_recorded at start of new session
        attendance_recorded.clear()
        
        recording_active = True
        
        if recording_timer and recording_timer.is_alive():
            recording_timer.cancel()
            
        recording_timer = Timer(5.0, stop_recording)  # Changed from 20.0 to 12.0
        recording_timer.start()
        
        return jsonify({
            "status": "success", 
            "message": "Recording started successfully",
            "face_recognized": False
        })
        
    except Exception as e:
        logger.error(f"Error starting recording: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Add new endpoint to check face recognition status
@attendance_bp.route('/check_face_status')
def check_face_status():
    if len(attendance_recorded) > 0:
        latest_usn = list(attendance_recorded)[-1]
        return jsonify({
            "face_recognized": True,
            "usn": latest_usn
        })
    return jsonify({
        "face_recognized": False
    })

@attendance_bp.route('/stop_recording', methods=['POST'])  # Change to POST method
def stop_recording():
    global recording_active, recording_timer
    recording_active = False
    if recording_timer and recording_timer.is_alive():
        recording_timer.cancel()
    logger.info("Recording stopped")
    return jsonify({"status": "success", "message": "Recording stopped"})
@attendance_bp.teardown_app_request
def cleanup_after_request(exception=None):
    # Don't release camera after each request, only when app shuts down
    pass  # Adding this line to fix the indentation error
@attendance_bp.route('/verify_otp', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        student_id = data.get('usn')
        otp = data.get('otp')
        
        # Add your OTP verification logic here
        if otp == "123456":  # Replace with actual OTP verification
            update_verification_status(student_id, 'otp')
            return jsonify({'success': True, 'message': 'OTP verified successfully'})
        return jsonify({'success': False, 'message': 'Invalid OTP'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


if __name__ == '__main__':
    # Create app only for standalone mode
    app = Flask(__name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'))
    CORS(app)
    
    # Register both blueprints
    app.register_blueprint(voice_bp, url_prefix='/voice')
    
    if init_face_recognition():
        app.register_blueprint(attendance_bp)
        app.run(host='0.0.0.0', port=5001, debug=True)
    else:
        logger.error("Failed to initialize face recognition system")
