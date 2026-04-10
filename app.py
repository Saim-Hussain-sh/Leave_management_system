from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import timedelta
from db import get_db_connection
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'jwt-dev-secret')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

jwt = JWTManager(app)

# CORS - Restrict to frontend URL in production
frontend_url = os.getenv('FRONTEND_URL', '*')
CORS(app, resources={r"/*": {"origins": frontend_url}})

@app.route('/')
def home():
    return jsonify({'message': 'Leave System API Running', 'version': '1.0'})

# ==================== AUTHENTICATION ====================

@app.route('/register', methods=['POST'])
def register():
    """Admin only - Register new employee"""
    data = request.json
    
    # Validate required fields
    required = ['name', 'email', 'password', 'role_id', 'admin_email']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin
        cursor.execute("SELECT role_id FROM tbl_users WHERE email = %s", (data['admin_email'],))
        admin = cursor.fetchone()
        if not admin or admin['role_id'] != 1:  # 1 = admin
            return jsonify({'error': 'Unauthorized. Admin access required'}), 403
        
        # Check if email exists
        cursor.execute("SELECT id FROM tbl_users WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            return jsonify({'error': 'Email already exists'}), 409
        
        # Hash password
        hashed_password = generate_password_hash(data['password'])
        
        # Insert user
        cursor.execute("""
            INSERT INTO tbl_users (name, email, password, role_id) 
            VALUES (%s, %s, %s, %s)
        """, (data['name'], data['email'], hashed_password, data['role_id']))
        
        conn.commit()
        
        return jsonify({
            'message': 'Employee registered successfully',
            'user_id': cursor.lastrowid
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT u.id, u.name, u.email, u.password, u.role_id, r.role_name 
            FROM tbl_users u
            JOIN lutbl_roles r ON u.role_id = r.role_id
            WHERE u.email = %s AND u.status = 1
        """, (email,))
        
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Create JWT token
        access_token = create_access_token(identity=user['id'])
        
        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'role': user['role_name']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ==================== EMPLOYEE ROUTES ====================

@app.route('/apply-leave', methods=['POST'])
@jwt_required()
def apply_leave():
    current_user_id = get_jwt_identity()
    data = request.json
    
    # Validation
    required = ['leave_type_id', 'start_date', 'end_date', 'reason']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check balance
        cursor.execute("""
            SELECT total_allowed, used 
            FROM tbl_leave_balance 
            WHERE user_id = %s AND leave_type_id = %s
        """, (current_user_id, data['leave_type_id']))
        
        balance = cursor.fetchone()
        if not balance:
            return jsonify({'error': 'Leave balance not found'}), 400
        
        if balance['used'] >= balance['total_allowed']:
            return jsonify({'error': 'Leave limit exceeded'}), 400
        
        # Insert leave (status_id 2 = pending)
        cursor.execute("""
            INSERT INTO tbl_leaves (user_id, start_date, end_date, reason, status_id, leave_type_id)
            VALUES (%s, %s, %s, %s, 2, %s)
        """, (current_user_id, data['start_date'], data['end_date'], 
              data['reason'], data['leave_type_id']))
        
        conn.commit()
        
        return jsonify({
            'message': 'Leave applied successfully',
            'leave_id': cursor.lastrowid
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/my-leaves', methods=['GET'])
@jwt_required()
def get_my_leaves():
    current_user_id = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT l.id, lt.type_name as leave_type, ls.status_name as status,
                   l.start_date, l.end_date, l.reason, l.created_at
            FROM tbl_leaves l
            JOIN lutbl_leave_types lt ON l.leave_type_id = lt.id
            JOIN lutbl_leave_status ls ON l.status_id = ls.id
            WHERE l.user_id = %s
            ORDER BY l.created_at DESC
        """, (current_user_id,))
        
        leaves = cursor.fetchall()
        return jsonify({'leaves': leaves}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ==================== ADMIN ROUTES ====================

@app.route('/admin/leaves', methods=['GET'])
@jwt_required()
def get_all_leaves():
    current_user_id = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin
        cursor.execute("SELECT role_id FROM tbl_users WHERE id = %s", (current_user_id,))
        user = cursor.fetchone()
        if not user or user['role_id'] != 1:
            return jsonify({'error': 'Unauthorized. Admin access required'}), 403
        
        cursor.execute("""
            SELECT l.id, u.name as employee_name, lt.type_name as leave_type,
                   ls.status_name as status, l.start_date, l.end_date, l.reason
            FROM tbl_leaves l
            JOIN tbl_users u ON l.user_id = u.id
            JOIN lutbl_leave_types lt ON l.leave_type_id = lt.id
            JOIN lutbl_leave_status ls ON l.status_id = ls.id
            ORDER BY l.created_at DESC
        """)
        
        leaves = cursor.fetchall()
        return jsonify({'leaves': leaves}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/update-leave-status/<int:leave_id>', methods=['PUT'])
@jwt_required()
def update_leave_status(leave_id):
    current_user_id = get_jwt_identity()
    data = request.json
    new_status_id = data.get('status_id')  # 1=approved, 3=rejected
    
    if new_status_id not in [1, 3]:
        return jsonify({'error': 'Invalid status. Use 1 for approve, 3 for reject'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin
        cursor.execute("SELECT role_id FROM tbl_users WHERE id = %s", (current_user_id,))
        admin = cursor.fetchone()
        if not admin or admin['role_id'] != 1:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Get leave details
        cursor.execute("SELECT * FROM tbl_leaves WHERE id = %s", (leave_id,))
        leave = cursor.fetchone()
        
        if not leave:
            return jsonify({'error': 'Leave not found'}), 404
        
        if leave['status_id'] != 2:  # 2 = pending
            return jsonify({'error': 'Leave already processed'}), 400
        
        # Update status
        cursor.execute("""
            UPDATE tbl_leaves SET status_id = %s WHERE id = %s
        """, (new_status_id, leave_id))
        
        # If approved, update balance
        if new_status_id == 1:
            cursor.execute("""
                UPDATE tbl_leave_balance 
                SET used = used + 1 
                WHERE user_id = %s AND leave_type_id = %s
            """, (leave['user_id'], leave['leave_type_id']))
        
        conn.commit()
        return jsonify({'message': 'Status updated successfully'}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/employees', methods=['GET'])
@jwt_required()
def get_all_employees():
    current_user_id = get_jwt_identity()
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin
        cursor.execute("SELECT role_id FROM tbl_users WHERE id = %s", (current_user_id,))
        user = cursor.fetchone()
        if not user or user['role_id'] != 1:
            return jsonify({'error': 'Unauthorized'}), 403
        
        cursor.execute("""
            SELECT u.id, u.name, u.email, r.role_name 
            FROM tbl_users u
            JOIN lutbl_roles r ON u.role_id = r.role_id
            WHERE u.id != %s AND u.status = 1
            ORDER BY u.id DESC
        """, (current_user_id,))
        
        employees = cursor.fetchall()
        return jsonify({'employees': employees}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/admin/employees/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_employee(user_id):
    current_user_id = get_jwt_identity()
    
    if user_id == current_user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verify admin
        cursor.execute("SELECT role_id FROM tbl_users WHERE id = %s", (current_user_id,))
        admin = cursor.fetchone()
        if not admin or admin['role_id'] != 1:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Soft delete (set status to 0 instead of hard delete)
        cursor.execute("UPDATE tbl_users SET status = 0 WHERE id = %s", (user_id,))
        conn.commit()
        
        return jsonify({'message': 'Employee deleted successfully'}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=False)  # debug=False for production