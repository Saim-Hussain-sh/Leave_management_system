from flask import Flask
from flask_cors import CORS
from flask import request , jsonify
from db import get_db_connection

app = Flask(__name__)
CORS(app,resources={r"/*":{"origins":"*"}})

@app.route('/')
def home():
    return 'Leave System API Running'


@app.route('/apply-leave' , methods=['POST'])
def apply_leave():
    data=request.json

    #input validation
    required_fields = ['user_id' , 'leave_type_id' , 'start_date' , 'end_date' , 'reason']

    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}" }), 400

    user_id = data['user_id']
    leave_type_id = data['leave_type_id']
    start_date = data ['start_date']
    end_date = data ['end_date']
    reason = data['reason']

    conn = get_db_connection()
    cursor=conn.cursor(dictionary=True)

    try:
        #Check balance
        cursor.execute("""
            SELECT total_allowed , used
            FROM tbl_leave_balance
            WHERE user_id = %s AND leave_type_id = %s
               """ , (user_id , leave_type_id))
    
        balance = cursor.fetchone()

        if not balance:
            return jsonify({"error": "Leave balance not found"}), 400
    
        if balance['used'] >= balance['total_allowed']:
            return jsonify({"error":"Leave limit exceeded"}), 400
    
        #step 2: Insert leave request(Pending)

        cursor.execute("""
                INSERT INTO tbl_leaves (user_id , start_date , end_date , reason , status_id , leave_type_id)
                VALUES (%s, %s, %s ,%s , 2 ,%s)
                """, (user_id , start_date , end_date , reason , leave_type_id))
    
        conn.commit()

        return jsonify({"message": "Leave applied successfully",
                        "leave_id": cursor.lastrowid}), 201
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    
    finally:
        cursor.close()
        conn.close()


@app.route('/admin/leaves' , methods = ['GET'])
def get_all_leaves():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query ="""
    SELECT
        l.id, u.name AS employee_name,
        lt.type_name AS leave_type,
        ls.status_name AS status,
        l.start_date,l.end_date,l.reason
        FROM tbl_leaves as l 
        JOIN tbl_users as u ON l.user_id = u.id
        JOIN lutbl_leave_types lt ON l.leave_type_id = lt.id
        JOIN lutbl_leave_status ls ON l.status_id = ls.id
        ORDER BY l.id DESC
        """
    
    try:
        cursor.execute(query)
        leaves = cursor.fetchall()

        return jsonify({"leaves": leaves}),200
    
    except Exception as e:
        return jsonify({'error': str(e)}),500
    
    finally:
        cursor.close()
        conn.close()


@app.route('/login',methods=["POST"])
def login():
    data=request.json
    email=data.get('email')
    password = data.get('password')  #In production hash this

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT u.id, u.name, u.email, r.role_name 
                       FROM tbl_users u
                       JOIN lutbl_roles r ON u.role_id = r.role_id
                       WHERE u.email = %s AND u.password = %s
                       """,(email,password))
        
        user = cursor.fetchone()

        if user:
            return jsonify({'message': 'Login successful',
                            'user': {
                                'id': user['id'],
                                'name': user['name'],
                                'email': user['email'],
                                'role': user['role_name']
                                }
                            }),200
        else:
            return jsonify({'error': "Invalid credentials"}),401
        
    except Exception as e:
        return jsonify({"error": str(e)}),500
    
    finally:
        cursor.close()
        conn.close()


@app.route('/my-leaves/<int:user_id>' , methods = ['GET'])
def get_my_leave(user_id):
    """for employees to view their own history"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT l.id , lt.type_name AS leave_type , ls.status_name AS status,
                       l.start_date , l.end_date, 
                       l.reason From tbl_leaves l 
                       JOIN lutbl_leave_types lt ON l.leave_type_id = lt.id
                       JOIN lutbl_leave_status ls ON l.status_id = ls.id
                       WHERE l.user_id = %s
                       ORDER BY l.id DESC""", (user_id,))
        
        leaves=cursor.fetchall()
        return jsonify({"leaves": leaves}),200
    
    except Exception as e:
        return jsonify({"error": str(e)}),500
    
    finally:
        cursor.close()
        conn.close()


@app.route('/update-leave-status/<int:leave_id>',methods = ["PUT"])
def update_leave_status(leave_id):
    """Admin approves or reject leave"""
    data = request.json
    new_status_id= data.get('status_id')#1 for approve and 3 for reject

    admin_id = data.get("admin_id")

    if not admin_id or not check_admin(admin_id):
        return jsonify({"error": "Unauthorized. Admin access required"}), 403
    
    if new_status_id not in [1,3]:
        return jsonify({'error': "Invalid status_id"}),400
    
    conn  = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM tbl_leaves WHERE id = %s", (leave_id,))
        leave= cursor.fetchone()

        if not leave:
            return jsonify({"error": 'Leave request not found'}),404
        

        cursor.execute("""
                UPDATE tbl_leaves SET status_id = %s
                       WHERE id = %s
                       """,(new_status_id , leave_id))
        
        if new_status_id == 1:
            # Calculate days (simplified - you might want exact calculation)
            cursor.execute("""
                UPDATE tbl_leave_balance 
                SET used = used + 1 
                WHERE user_id = %s AND leave_type_id = %s
            """, (leave['user_id'], leave['leave_type_id']))
        
        conn.commit()
        return jsonify({"message": "Leave status updated successfully"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()   

#Helper function to check user is admin
def check_admin(admin_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.role_name FROM tbl_users u 
                       JOIN lutbl_roles r ON u.role_id=
                       r.role_id WHERE u.id = %s""",(admin_id,))

        user = cursor.fetchone()
        return user and user['role_name'] == 'admin'
    
    finally:
        cursor.close()
        conn.close()

#1. GET all employees(Admin only)
@app.route('/admin/employees',methods=['GET'])
def get_all_employees():
    admin_id = request.args.get('admin_id', type = int)

    if not admin_id or not check_admin(admin_id):
        return jsonify({'error': 'Unauthorized. Admin access required'}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT u.id , u.name , u.email , r.role_name
                       FROM tbl_users u 
                       JOIN lutbl_roles r ON 
                       u.role_id = r.role_id
                       WHERE u.id !=%s 
                       ORDER BY u.id DESC""",(admin_id,))
        employees = cursor.fetchall()
        return jsonify({"employees": employees}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


#2. POST add new employee (Admin only)
@app.route('/admin/employees',methods=['POST'])
def add_employee():
    data = request.json
    admin_id = data.get('admin_id')

    if not admin_id or not check_admin(admin_id):
        return jsonify({"error": "Unauthorized. Admin access required"}),403
    
    #Required fields
    required = ['name', 'email', 'password', 'role_id']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
        

    conn = get_db_connection()
    cursor= conn.cursor(dictionary=True)

    try:
        #check if email already exists
        cursor.execute("""
            SELECT id FROM tbl_users WHERE email = %s""",(data['email'],))
        if cursor.fetchone():
            return jsonify({"error": 'Email already exists'}),409
        
        cursor.execute("""
            INSERT INTO tbl_users (name,email,password,role_id)
                       VALUES (%s,%s,%s,%s)""",(data['name'],data['email'],data['password'],data['role_id']))
        
        conn.commit()
        return jsonify({'message': "Employee added successfully",
                        "user_id": cursor.lastrowid}),201
    
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# 3. PUT update employee (Admin only)
@app.route('/admin/employees/<int:user_id>', methods=['PUT'])
def update_employee(user_id):
    data = request.json
    admin_id = data.get('admin_id')
    
    if not admin_id or not check_admin(admin_id):
        return jsonify({"error": "Unauthorized. Admin access required"}), 403
    
    # Fields that can be updated
    allowed_fields = ['name', 'email', 'password', 'role_id']
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM tbl_users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Employee not found"}), 404
        
        # Check email uniqueness if updating email
        if 'email' in updates:
            cursor.execute("SELECT id FROM tbl_users WHERE email = %s AND id != %s", 
                          (updates['email'], user_id))
            if cursor.fetchone():
                return jsonify({"error": "Email already exists"}), 409
        
        # Build dynamic query
        set_clause = ", ".join([f"{field} = %s" for field in updates.keys()])
        values = list(updates.values()) + [user_id]
        
        cursor.execute(f"UPDATE tbl_users SET {set_clause} WHERE id = %s", values)
        conn.commit()
        
        return jsonify({"message": "Employee updated successfully"}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# 4. DELETE employee (Admin only)
@app.route('/admin/employees/<int:user_id>', methods=['DELETE'])
def delete_employee(user_id):
    data = request.json or {}
    admin_id = data.get('admin_id') or request.args.get('admin_id', type=int)
    
    if not admin_id or not check_admin(admin_id):
        return jsonify({"error": "Unauthorized. Admin access required"}), 403
    
    # Prevent admin from deleting themselves
    if user_id == admin_id:
        return jsonify({"error": "Cannot delete your own account"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Check if user exists
        cursor.execute("SELECT id FROM tbl_users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Employee not found"}), 404
        
        # Option 1: Hard delete
        cursor.execute("DELETE FROM tbl_users WHERE id = %s", (user_id,))
        
        # Option 2: Soft delete (if you have status column)
        # cursor.execute("UPDATE tbl_users SET status = 0 WHERE id = %s", (user_id,))
        
        conn.commit()
        return jsonify({"message": "Employee deleted successfully"}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
            
                   



if __name__ == '__main__':
    app.run(debug=True)


