from fastapi import FastAPI, Depends, HTTPException, status, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
import os
from dotenv import load_dotenv

from db import SessionLocal
from models import User, Role, Leave, LeaveType, LeaveStatus, LeaveBalance

load_dotenv()

# ==================== CONFIGURATION ====================
SECRET_KEY=os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

app = FastAPI(
    title="Leave System API",
    version="2.0 FastAPI",
    description="Converted from Flask to FastAPI"
)

# CORS Middleware
frontend_url = os.getenv('FRONTEND_URL', '*')
origins = ["*"] if frontend_url == '*' else [frontend_url]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== PYDANTIC SCHEMAS ====================
class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    role_id: int
    admin_email: str

class UserLogin(BaseModel):
    email: str
    password: str

class LeaveApply(BaseModel):
    leave_type_id: int
    start_date: str
    end_date: str
    reason: str

class LeaveStatusUpdate(BaseModel):
    status_id: int

# ==================== DATABASE DEPENDENCY ====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==================== JWT UTILITIES ====================
from datetime import timezone

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ==================== SECURITY ====================
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id), User.status == 1).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    if current_user.role_id != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# ==================== ROUTES ====================

@app.post("/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email, status=1).first()

    if not user or not user.check_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    return {
        "message": "Login successful",
        "access_token": access_token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.role_name if user.role else "unknown"
        }
    }

@app.get("/")
def home():
    return {"message": "Leave System API Running", "version": "2.0 SQLAlchemy FastAPI"}

# ==================== AUTHENTICATION ====================

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """Admin only - Register new employee"""

    admin = db.query(User).filter_by(email=data.admin_email, role_id=1).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized. Admin access required"
        )

    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists"
        )

    new_user = User(
        name=data.name,
        email=data.email,
        role_id=data.role_id,
        status=1
    )
    new_user.set_password(data.password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "Employee registered successfully",
        "user_id": new_user.id
    }
# ==================== EMPLOYEE ROUTES ====================

@app.post("/apply-leave", status_code=status.HTTP_201_CREATED)
def apply_leave(
    data: LeaveApply,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    balance = db.query(LeaveBalance).filter_by(
        user_id=current_user.id,
        leave_type_id=data.leave_type_id,
        status=1
    ).first()

    if not balance:
        raise HTTPException(status_code=400, detail="Leave balance not found")

    if balance.used >= balance.total_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Leave limit exceeded. Available: {balance.total_allowed - balance.used}"
        )

    new_leave = Leave(
        user_id=current_user.id,
        leave_type_id=data.leave_type_id,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status_id=2,
        status=1
    )

    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)

    return {"message": "Leave applied successfully", "leave_id": new_leave.id}


@app.get("/my-leaves")
def get_my_leaves(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    leaves = db.query(Leave).filter_by(user_id=current_user.id).order_by(Leave.created_at.desc()).all()

    result = []
    for leave in leaves:
        result.append({
            "id": leave.id,
            "leave_type": leave.leave_type.type_name if leave.leave_type else "Unknown",
            "status": leave.leave_status.status_name if leave.leave_status else "Unknown",
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "reason": leave.reason,
            "created_at": str(leave.created_at)
        })

    return {"leaves": result}


@app.get("/my-balance")
def get_my_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    balances = db.query(LeaveBalance).filter_by(user_id=current_user.id).all()

    result = []
    for bal in balances:
        result.append({
            "leave_type": bal.leave_type.type_name if bal.leave_type else "Unknown",
            "total_allowed": bal.total_allowed,
            "used": bal.used,
            "remaining": bal.total_allowed - bal.used
        })

    return {"balances": result}


# ==================== ADMIN ROUTES ====================

@app.get("/admin/leaves")
def get_all_leaves(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    leaves = db.query(Leave).order_by(Leave.created_at.desc()).all()

    result = []
    for leave in leaves:
        result.append({
            "id": leave.id,
            "employee_name": leave.user.name if leave.user else "Unknown",
            "leave_type": leave.leave_type.type_name if leave.leave_type else "Unknown",
            "status": leave.leave_status.status_name if leave.leave_status else "Unknown",
            "start_date": str(leave.start_date),
            "end_date": str(leave.end_date),
            "reason": leave.reason
        })

    return {"leaves": result}


@app.put("/update-leave-status/{leave_id}")
def update_leave_status(
    leave_id: int,
    data: LeaveStatusUpdate,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if data.status_id not in [1, 3]:
        raise HTTPException(status_code=400, detail="Invalid status")

    leave = db.query(Leave).filter_by(id=leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    if leave.status_id != 2:
        raise HTTPException(status_code=400, detail="Already processed")

    leave.status_id = data.status_id

    if data.status_id == 1:
        balance = db.query(LeaveBalance).filter_by(
            user_id=leave.user_id,
            leave_type_id=leave.leave_type_id
        ).first()
        if balance:
            balance.used += 1

    db.commit()
    return {"message": "Status updated successfully"}


@app.get("/admin/employees")
def get_all_employees(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    print(f"Auth Header: {request.headers.get('authorization')}")
    print(f"User: {current_admin.email}, Role: {current_admin.role_id}")
    employees = db.query(User).filter(
        User.id != current_admin.id,
        User.status == 1
    ).all()

    result = []
    for emp in employees:
        result.append({
            "id": emp.id,
            "name": emp.name,
            "email": emp.email,
            "role": emp.role.role_name if emp.role else "unknown"
        })

    return {"employees": result}


@app.delete("/admin/employees/{user_id}")
def delete_employee(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    employee = db.query(User).filter_by(id=user_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.status = 0
    db.commit()

    return {"message": "Employee deleted successfully"}

# ==================== RUN ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)