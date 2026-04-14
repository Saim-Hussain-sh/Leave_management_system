from db import engine, Base
from models import Role, LeaveType, LeaveStatus, User, Leave, LeaveBalance
from sqlalchemy.orm import Session

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created!")

# Seed reference data
db = Session(bind=engine)

try:
    # Check if data already exists
    if not db.query(Role).first():
        print("Seeding roles...")
        roles = [
            Role(role_id=1, role_name='admin', status=1),
            Role(role_id=2, role_name='employee', status=1)
        ]
        db.add_all(roles)
        db.commit()
        print("✅ Roles added")
    
    if not db.query(LeaveType).first():
        print("Seeding leave types...")
        types = [
            LeaveType(id=1, type_name='casual', status=1),
            LeaveType(id=2, type_name='medical', status=1)
        ]
        db.add_all(types)
        db.commit()
        print("✅ Leave types added")
    
    if not db.query(LeaveStatus).first():
        print("Seeding leave statuses...")
        statuses = [
            LeaveStatus(id=1, status_name='approved', status=1),
            LeaveStatus(id=2, status_name='pending', status=1),
            LeaveStatus(id=3, status_name='rejected', status=1)
        ]
        db.add_all(statuses)
        db.commit()
        print("✅ Leave statuses added")
    
    # Create default admin if not exists
    if not db.query(User).filter_by(email='admin@company.com').first():
        print("Creating default admin...")
        admin = User(
            name='System Admin',
            email='admin@company.com',
            role_id=1,
            status=1
        )
        admin.set_password('admin123')  # Change this in production!
        db.add(admin)
        db.commit()
        print("✅ Default admin created (admin@company.com / admin123)")
    
    print("\n🎉 Database initialized successfully!")
    print("You can now start the Flask app")

except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()