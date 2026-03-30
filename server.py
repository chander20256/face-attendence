from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
import base64
import shutil

app = Flask(__name__)
CORS(app)

# Data storage paths
DATA_DIR = 'data'
STUDENTS_FILE = os.path.join(DATA_DIR, 'students.json')
ATTENDANCE_FILE = os.path.join(DATA_DIR, 'attendance.json')
FACE_IMAGES_DIR = os.path.join(DATA_DIR, 'face_images')

# Create directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FACE_IMAGES_DIR, exist_ok=True)

# ===================================================================
# DATA LOAD/SAVE FUNCTIONS
# ===================================================================
def load_students():
    """Load all students from JSON file"""
    if os.path.exists(STUDENTS_FILE):
        with open(STUDENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_students(students):
    """Save students to JSON file"""
    with open(STUDENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(students, f, indent=2, ensure_ascii=False)

def load_attendance():
    """Load attendance records"""
    if os.path.exists(ATTENDANCE_FILE):
        with open(ATTENDANCE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_attendance(attendance):
    """Save attendance records"""
    with open(ATTENDANCE_FILE, 'w', encoding='utf-8') as f:
        json.dump(attendance, f, indent=2, ensure_ascii=False)

def save_face_image(roll_no, index, image_base64):
    """Save face image as file"""
    student_face_dir = os.path.join(FACE_IMAGES_DIR, roll_no)
    os.makedirs(student_face_dir, exist_ok=True)
    
    filename = f"face_{index+1}.txt"
    filepath = os.path.join(student_face_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(image_base64)
    
    return filepath

# ===================================================================
# API ENDPOINTS
# ===================================================================
@app.route('/api/register', methods=['POST'])
def register_student():
    """Register a new student with all data and face images"""
    try:
        data = request.json
        
        # Extract student information
        roll_no = data.get('studentId', '').strip()
        first_name = data.get('firstName', '').strip()
        last_name = data.get('lastName', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        dob = data.get('dob', '')
        gender = data.get('gender', '')
        dept = data.get('dept', '')
        year = data.get('year', '')
        password = data.get('password', '')
        emergency_name = data.get('emergencyName', '').strip()
        emergency_phone = data.get('emergencyPhone', '').strip()
        address = data.get('address', '').strip()
        profile_photo = data.get('profilePhoto', '')
        face_images = data.get('faceImages', [])
        
        # Validate required fields
        if not roll_no:
            return jsonify({'success': False, 'message': 'Roll number is required'}), 400
        
        if not first_name:
            return jsonify({'success': False, 'message': 'First name is required'}), 400
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        
        if not password:
            return jsonify({'success': False, 'message': 'Password is required'}), 400
        
        if len(face_images) < 5:
            return jsonify({'success': False, 'message': f'Please capture all 5 face images (got {len(face_images)})'}), 400
        
        # Load existing students
        students = load_students()
        
        # Check if student already exists
        if roll_no in students:
            return jsonify({'success': False, 'message': f'Student with roll number {roll_no} already exists!'}), 400
        
        # Prepare student data
        student_data = {
            'roll_no': roll_no,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': f"{first_name} {last_name}".strip(),
            'email': email,
            'phone': phone,
            'dob': dob,
            'gender': gender,
            'department': dept,
            'year': year,
            'password': password,
            'emergency_name': emergency_name,
            'emergency_phone': emergency_phone,
            'address': address,
            'profile_photo': profile_photo[:100] + '...' if profile_photo else None,
            'face_images_count': len(face_images),
            'registered_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'registered_timestamp': datetime.now().isoformat()
        }
        
        # Save student data
        students[roll_no] = student_data
        save_students(students)
        
        # Save all face images as files
        saved_faces = []
        for i, img_base64 in enumerate(face_images):
            filepath = save_face_image(roll_no, i, img_base64)
            saved_faces.append(filepath)
        
        print(f"✅ Student registered: {first_name} {last_name} ({roll_no})")
        print(f"📸 Saved {len(saved_faces)} face images")
        
        return jsonify({
            'success': True,
            'message': f'Registration successful! Welcome {first_name} {last_name}',
            'student_id': roll_no,
            'face_images_saved': len(saved_faces)
        })
        
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login_student():
    """Student login and mark attendance"""
    try:
        data = request.json
        roll_no = data.get('rollNo', '').strip()
        password = data.get('password', '')
        
        if not roll_no or not password:
            return jsonify({'success': False, 'message': 'Roll number and password required'}), 400
        
        students = load_students()
        
        # Check if student exists
        if roll_no not in students:
            return jsonify({'success': False, 'message': 'Student not found! Please register first.'}), 404
        
        student = students[roll_no]
        
        # Check password
        if student.get('password') != password:
            return jsonify({'success': False, 'message': 'Invalid password!'}), 401
        
        # Mark attendance for today
        today = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M:%S')
        
        attendance = load_attendance()
        
        # Check if already marked today
        if today in attendance and roll_no in attendance[today]:
            return jsonify({
                'success': True,
                'student': {
                    'name': student['full_name'],
                    'roll_no': roll_no,
                    'dept': student.get('department', ''),
                    'year': student.get('year', ''),
                    'email': student.get('email', '')
                },
                'message': f'Welcome back {student["full_name"]}! You already marked attendance today at {attendance[today][roll_no]["time"]}',
                'already_marked': True
            })
        
        # Mark attendance
        if today not in attendance:
            attendance[today] = {}
        
        attendance[today][roll_no] = {
            'name': student['full_name'],
            'roll_no': roll_no,
            'time': current_time,
            'date': today,
            'status': 'present',
            'department': student.get('department', ''),
            'year': student.get('year', '')
        }
        
        save_attendance(attendance)
        
        return jsonify({
            'success': True,
            'student': {
                'name': student['full_name'],
                'roll_no': roll_no,
                'dept': student.get('department', ''),
                'year': student.get('year', ''),
                'email': student.get('email', '')
            },
            'message': f'✅ Attendance marked for {student["full_name"]} at {current_time}',
            'already_marked': False
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/students', methods=['GET'])
def get_all_students():
    """Get all registered students"""
    try:
        students = load_students()
        student_list = []
        
        for roll_no, data in students.items():
            student_list.append({
                'roll_no': roll_no,
                'name': data.get('full_name', data.get('name', '')),
                'department': data.get('department', ''),
                'year': data.get('year', ''),
                'email': data.get('email', ''),
                'registered_date': data.get('registered_date', '')
            })
        
        return jsonify({
            'success': True,
            'students': student_list,
            'total': len(student_list)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/attendance/today', methods=['GET'])
def get_today_attendance():
    """Get today's attendance records"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        attendance = load_attendance()
        
        today_data = attendance.get(today, {})
        entries = []
        
        for roll_no, data in today_data.items():
            entries.append({
                'roll_no': roll_no,
                'name': data.get('name', ''),
                'time': data.get('time', ''),
                'department': data.get('department', ''),
                'year': data.get('year', '')
            })
        
        return jsonify({
            'success': True,
            'entries': entries,
            'total': len(entries),
            'date': today
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/student/<roll_no>', methods=['GET'])
def get_student_details(roll_no):
    """Get complete student details including face images"""
    try:
        students = load_students()
        
        if roll_no not in students:
            return jsonify({'success': False, 'message': 'Student not found'}), 404
        
        student = students[roll_no]
        
        # Get face images (just count, not full images)
        student_face_dir = os.path.join(FACE_IMAGES_DIR, roll_no)
        face_count = 0
        if os.path.exists(student_face_dir):
            face_count = len([f for f in os.listdir(student_face_dir) if f.endswith('.txt')])
        
        # Get attendance stats
        attendance = load_attendance()
        total_present = 0
        total_days = 0
        
        for date, records in attendance.items():
            if roll_no in records:
                total_present += 1
            total_days += 1
        
        attendance_percentage = (total_present / total_days * 100) if total_days > 0 else 0
        
        return jsonify({
            'success': True,
            'student': {
                'roll_no': roll_no,
                'name': student.get('full_name', ''),
                'first_name': student.get('first_name', ''),
                'last_name': student.get('last_name', ''),
                'email': student.get('email', ''),
                'phone': student.get('phone', ''),
                'department': student.get('department', ''),
                'year': student.get('year', ''),
                'registered_date': student.get('registered_date', ''),
                'face_images_count': face_count
            },
            'attendance_stats': {
                'total_present': total_present,
                'total_days': total_days,
                'percentage': round(attendance_percentage, 2)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    students = load_students()
    attendance = load_attendance()
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'statistics': {
            'total_students': len(students),
            'total_attendance_records': sum(len(records) for records in attendance.values()),
            'data_directory': DATA_DIR
        }
    })

@app.route('/api/face-images/<roll_no>', methods=['GET'])
def get_face_images(roll_no):
    """Get face images for a student (for recognition)"""
    try:
        student_face_dir = os.path.join(FACE_IMAGES_DIR, roll_no)
        
        if not os.path.exists(student_face_dir):
            return jsonify({'success': False, 'message': 'No face images found'}), 404
        
        face_images = []
        for filename in sorted(os.listdir(student_face_dir)):
            if filename.endswith('.txt'):
                filepath = os.path.join(student_face_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    img_base64 = f.read()
                    face_images.append(img_base64)
        
        return jsonify({
            'success': True,
            'roll_no': roll_no,
            'face_images': face_images,
            'count': len(face_images)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/clear', methods=['POST'])
def clear_database():
    """Clear all data (for testing purposes)"""
    try:
        # Clear students data
        save_students({})
        
        # Clear attendance data
        save_attendance({})
        
        # Clear face images directory
        if os.path.exists(FACE_IMAGES_DIR):
            shutil.rmtree(FACE_IMAGES_DIR)
            os.makedirs(FACE_IMAGES_DIR, exist_ok=True)
        
        print("🗑️ All data cleared successfully!")
        
        return jsonify({
            'success': True, 
            'message': 'All data cleared successfully!'
        })
    except Exception as e:
        print(f"Clear database error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/add-demo', methods=['POST'])
def add_demo_student():
    """Add a demo student for testing"""
    try:
        roll_no = "22CS001"
        
        # Check if already exists
        students = load_students()
        if roll_no in students:
            return jsonify({
                'success': False,
                'message': 'Demo student already exists! Try logging in with Roll: 22CS001, Password: password123'
            }), 400
        
        # Create demo student
        demo_student = {
            'roll_no': roll_no,
            'first_name': 'Aarav',
            'last_name': 'Sharma',
            'full_name': 'Aarav Sharma',
            'email': 'aarav@example.com',
            'phone': '9876543210',
            'dob': '2002-01-15',
            'gender': 'Male',
            'department': 'Computer Science',
            'year': '3rd Year',
            'password': 'password123',
            'emergency_name': 'Raj Sharma',
            'emergency_phone': '9988776655',
            'address': '123 College Road, Delhi',
            'profile_photo': None,
            'face_images_count': 0,
            'registered_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'registered_timestamp': datetime.now().isoformat()
        }
        
        students[roll_no] = demo_student
        save_students(students)
        
        print(f"✅ Demo student added: Aarav Sharma (22CS001)")
        
        return jsonify({
            'success': True,
            'message': 'Demo student added successfully!',
            'credentials': {
                'roll_no': '22CS001',
                'password': 'password123'
            }
        })
        
    except Exception as e:
        print(f"Add demo error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ===================================================================
# MAIN
# ===================================================================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🎯 FACE ATTENDANCE SYSTEM - BACKEND SERVER")
    print("="*60)
    print("\n✅ Server is running!")
    print(f"📁 Data directory: {DATA_DIR}")
    print("\n📋 API Endpoints:")
    print("   POST   /api/register        - Register new student")
    print("   POST   /api/login           - Login & mark attendance")
    print("   GET    /api/students        - Get all students")
    print("   GET    /api/attendance/today - Today's attendance")
    print("   GET    /api/student/<roll>  - Get student details")
    print("   GET    /api/face-images/<roll> - Get face images")
    print("   GET    /api/health          - Health check")
    print("   POST   /api/clear           - Clear all data (testing)")
    print("   POST   /api/add-demo        - Add demo student")
    print("\n🌐 Server URL: http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)