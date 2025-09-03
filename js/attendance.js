$(document).ready(function() {
    let isRecording = false;
    let timer = null;
    let stream = null;
    let recognitionInterval = null;
    const TIMEOUT_SECONDS = 60;
    
    // Initialize branch-section mapping
    const branchSections = {
        'AIML': ['A'],
        'CSE': ['A', 'B', 'C', 'D'],
        'ECE': ['A', 'B'],
        'ISE': ['A', 'B']
    };

    // Populate sections when branch changes
    $('#branch').change(function() {
        const branch = $(this).val();
        const sections = branchSections[branch] || [];
        const sectionSelect = $('#section');
        
        sectionSelect.empty();
        sectionSelect.append('<option value="">Select Section</option>');
        sections.forEach(section => {
            sectionSelect.append(`<option value="${section}">Section ${section}</option>`);
        });
    });

    // Populate semesters
    const semesterSelect = $('#semester');
    semesterSelect.empty();
    semesterSelect.append('<option value="">Select Semester</option>');
    for(let i = 1; i <= 8; i++) {
        semesterSelect.append(`<option value="${i}">${i}</option>`);
    }

    // Start Recognition Button
    $('#startRecognition').click(async function() {
        const branch = $('#branch').val();
        const section = $('#section').val();
        const semester = $('#semester').val();

        if (!branch || !section || !semester) {
            alert('Please select Branch, Section and Semester');
            return;
        }

        try {
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: {
                    width: 640,
                    height: 480
                },
                audio: false 
            });
            
            const videoElement = document.getElementById('video');
            videoElement.srcObject = stream;
            
            isRecording = true;
            $(this).prop('disabled', true);
            $('#stopRecognition').prop('disabled', false);
            $('#recognitionStatus').text('Camera initialized. Starting recognition...');
            
            // Reset and start timer
            clearInterval(timer);
            let timeLeft = TIMEOUT_SECONDS;
            updateTimer(timeLeft);
            
            timer = setInterval(() => {
                timeLeft--;
                if (timeLeft >= 0) {
                    updateTimer(timeLeft);
                }
                if (timeLeft <= 0) {
                    stopRecording();
                }
            }, 1000);

            startRecognition();
        } catch (err) {
            console.error('Error accessing camera:', err);
            $('#recognitionStatus').text('Error accessing camera. Please check permissions.');
            stopRecording();
        }
    });

    function startRecognition() {
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        const videoElement = document.getElementById('video');
        canvas.width = 640;
        canvas.height = 480;

        recognitionInterval = setInterval(() => {
            if (!isRecording) return;

            context.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
            const imageData = canvas.toDataURL('image/jpeg');

            const branch = $('#branch').val();
            const section = $('#section').val();
            const semester = $('#semester').val();

            $.ajax({
                url: '/process_attendance',
                method: 'POST',
                data: {
                    image: imageData,
                    branch: branch,
                    section: section,
                    semester: semester
                },
                success: function(data) {
                    if (data.recognized) {
                        $('#recognitionStatus').text(`Recognized: ${data.student_data.name} (${data.student_data.usn})`);
                        updateAttendanceTable(data.student_data);
                    } else {
                        $('#recognitionStatus').text('Scanning...');
                    }
                },
                error: function(error) {
                    console.error('Recognition error:', error);
                    $('#recognitionStatus').text('Recognition error occurred');
                }
            });
        }, 1000);
    }

    $('#stopRecognition').click(function() {
        stopRecording();
    });

    function startRecording() {
        fetch('/start_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Recording started');
            } else {
                console.error('Failed to start recording:', data.message);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function stopRecording() {
        fetch('/stop_recording', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Recording stopped');
            } else {
                console.error('Failed to stop recording:', data.message);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function stopRecording() {
        isRecording = false;
        if (recognitionInterval) {
            clearInterval(recognitionInterval);
        }
        if (timer) {
            clearInterval(timer);
        }
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }

        fetch('/attendance/stop_recording', {  // Update the endpoint path
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to stop recording');
            }
            return response.json();
        })
        .then(data => {
            console.log('Recording stopped successfully:', data);
            $('#recognitionStatus').text('Recording stopped successfully');
        })
        .catch(error => {
            console.error('Error stopping recording:', error);
            $('#recognitionStatus').text('Error stopping recording');
        });

        const videoElement = document.getElementById('video');
        videoElement.srcObject = null;
        $('#stopRecognition').prop('disabled', true);
        $('#startRecognition').prop('disabled', false);
        $('#timer').text('Time Remaining: 00:00');
    }

    function updateTimer(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        $('#timer').text(`Time Remaining: ${minutes}:${remainingSeconds.toString().padStart(2, '0')}`);
    }

    function updateAttendanceTable(studentData) {
        const tbody = $('#attendanceTable tbody');
        const existingRow = tbody.find(`tr:contains('${studentData.usn}')`);

        if (existingRow.length === 0) {
            const row = `
                <tr>
                    <td>${studentData.usn}</td>
                    <td>${studentData.name}</td>
                    <td>${new Date().toLocaleTimeString()}</td>
                    <td><span class="status-badge present">Present</span></td>
                </tr>
            `;
            tbody.append(row);
            $('#presentCount').text(parseInt($('#presentCount').text()) + 1);
        }
    }

    // Export attendance to CSV
    $('#exportAttendance').click(function() {
        // ... existing export code ...
    });
});
let video = document.getElementById('video');
let canvas = document.getElementById('canvas');
let context = canvas.getContext('2d');
let recognitionInterval;
let isRecognitionActive = false;

// Initialize camera
async function initializeCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
    } catch (err) {
        console.error("Error accessing camera:", err);
        alert("Could not access camera. Please check permissions.");
    }
}

// Start face recognition
async function startRecognition() {
    isRecognitionActive = true;
    document.getElementById('startRecognition').disabled = true;
    document.getElementById('stopRecognition').disabled = false;
    
    recognitionInterval = setInterval(() => {
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageData = canvas.toDataURL('image/jpeg');
        
        // Send frame to backend for recognition
        fetch('/process_frame', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image: imageData,
                branch: document.getElementById('branch').value,
                section: document.getElementById('section').value,
                semester: document.getElementById('semester').value
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.recognized_students) {
                updateAttendanceTable(data.recognized_students);
            }
        })
        .catch(err => console.error("Recognition error:", err));
    }, 1000); // Process every second
}

// Update attendance table
function updateAttendanceTable(recognizedStudents) {
    const tbody = document.querySelector('#attendanceTable tbody');
    
    recognizedStudents.forEach(student => {
        // Check if student is already marked
        if (!document.querySelector(`tr[data-usn="${student.usn}"]`)) {
            const row = document.createElement('tr');
            row.setAttribute('data-usn', student.usn);
            
            row.innerHTML = `
                <td>${student.usn}</td>
                <td>${student.name}</td>
                <td>${new Date().toLocaleTimeString()}</td>
                <td>Present</td>
            `;
            
            tbody.appendChild(row);
            updateAttendanceCounts();
        }
    });
}

// Initialize everything
document.addEventListener('DOMContentLoaded', () => {
    initializeCamera();
    
    document.getElementById('startRecognition').addEventListener('click', startRecognition);
    document.getElementById('stopRecognition').addEventListener('click', () => {
        clearInterval(recognitionInterval);
        isRecognitionActive = false;
        document.getElementById('startRecognition').disabled = false;
        document.getElementById('stopRecognition').disabled = true;
    });
});