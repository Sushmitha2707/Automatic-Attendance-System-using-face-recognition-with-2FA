@voice_bp.route('/send_otp', methods=['POST'])
def send_otp():
    try:
        data = request.get_json()
        usn = data.get('usn')
        
        # Get student email from database
        student = Student.query.filter_by(usn=usn).first()
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})
            
        # Generate and send OTP
        otp = generate_otp()  # Your OTP generation function
        send_email(student.email, otp)  # Your email sending function
        
        # Store OTP in session or database
        session[f'otp_{usn}'] = otp
        
        return jsonify({'success': True, 'message': 'OTP sent successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})