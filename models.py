from sqlalchemy import Column, Integer, String, Date, Text, TIMESTAMP, ForeignKey, text
from sqlalchemy.orm import relationship
from db import Base
import bcrypt   

class Role(Base):
    __tablename__ = "lutbl_roles"

    role_id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String(50), unique=True, nullable=False)
    status = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))

    users = relationship("User", back_populates="role")


class LeaveType(Base):
    __tablename__ = "lutbl_leave_types"

    id = Column(Integer, primary_key=True, index=True)
    type_name = Column(String(50), unique=True, nullable=False)
    status = Column(Integer, default=1)

    leaves = relationship("Leave", back_populates="leave_type")
    balances = relationship("LeaveBalance", back_populates="leave_type")


class LeaveStatus(Base):
    __tablename__ = "lutbl_leave_status"

    id = Column(Integer, primary_key=True, index=True)
    status_name = Column(String(50), unique=True, nullable=False)
    status = Column(Integer, default=1)

    leaves = relationship("Leave", back_populates="leave_status")


class User(Base):
    __tablename__ = "tbl_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100))
    email = Column(String(100), unique=True, index=True)
    password = Column(String(255))
    role_id = Column(Integer, ForeignKey("lutbl_roles.role_id"), nullable=False)
    status = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))

    role = relationship("Role", back_populates="users")
    leaves = relationship("Leave", back_populates="user")
    balances = relationship("LeaveBalance", back_populates="user")

    def set_password(self, plain_password):
        """Hash password using bcrypt"""
        self.password = bcrypt.hashpw(
            plain_password.encode('utf-8'), 
            bcrypt.gensalt()
        ).decode('utf-8')

    def check_password(self, plain_password):
        """Verify password against bcrypt hash"""
        if not self.password:
            return False
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            self.password.encode('utf-8')
        )


class Leave(Base):
    __tablename__ = "tbl_leaves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("tbl_users.id"), nullable=False)
    leave_type_id = Column(Integer, ForeignKey("lutbl_leave_types.id"), default=1)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=False)

    status_id = Column(Integer, ForeignKey("lutbl_leave_status.id"))
    status = Column(Integer, default=1)

    # ✅ FIX ADDED (this was missing and used in your API)
    created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))

    user = relationship("User", back_populates="leaves")
    leave_type = relationship("LeaveType", back_populates="leaves")
    leave_status = relationship("LeaveStatus", back_populates="leaves")


class LeaveBalance(Base):
    __tablename__ = "tbl_leave_balance"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("tbl_users.id"))
    leave_type_id = Column(Integer, ForeignKey("lutbl_leave_types.id"))
    total_allowed = Column(Integer)
    used = Column(Integer, default=0)
    status = Column(Integer, default=1)

    user = relationship("User", back_populates="balances")
    leave_type = relationship("LeaveType", back_populates="balances")