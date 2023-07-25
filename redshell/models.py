from sqlalchemy import Column, ForeignKey, Integer, String, Table, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Target(Base):
    __tablename__ = 'target_t'

    id = Column(Integer, primary_key=True)
    ip_addr = Column(String, unique=True)
    hostname = Column(String, unique=True)
    path = Column(String)
    os_name = Column(String)
    os_version = Column(String)
    arch = Column(String)
    virtual_machine = Column(String)

    credentials = relationship("Credential", secondary="target_cred", backref='targets')
    methods = relationship("Method", back_populates="target")
    commands = relationship("Command", back_populates="target")

class Credential(Base):
    __tablename__ = 'credential_t'

    id = Column(Integer, primary_key=True)
    username = Column(String)
    ctype = Column(String)
    cred = Column(String)
    domain = Column(String)
    origin = Column(String)
    time_created = Column(DateTime(timezone=True), server_default=func.now())

    methods = relationship("Method", back_populates="credential")

class Method(Base):
    __tablename__ = "method_t"

    id = Column(Integer, primary_key=True)
    method_type = Column(String)
    status = Column(String)

    target_id = Column(String, ForeignKey("target_t.id"), nullable=False)
    cred_id = Column(Integer, ForeignKey("credential_t.id"), nullable=False)
    tunnel_id = Column(Integer, ForeignKey("tunnel_t.id"), nullable=True)
    target = relationship("Target", back_populates="methods")
    credential = relationship("Credential", back_populates="methods")
    tunnel = relationship("Tunnel", back_populates="methods")

class Tunnel(Base):
    __tablename__ = 'tunnel_t'

    id = Column(Integer, primary_key=True)
    ip_addr = Column(String)
    port = Column(Integer)
    tunnel_type = Column(String)

    methods = relationship("Method", back_populates="tunnel")

class Command(Base):
    __tablename__ = "command_t"

    id = Column(Integer, primary_key=True)
    command_line = Column(String)
    result = Column(String)
    time_run = Column(DateTime(timezone=True), server_default=func.now())

    target_id = Column(String, ForeignKey("target_t.id"), nullable=False)
    target = relationship("Target", back_populates="commands")

target_cred_table = Table(
    "target_cred",
    Base.metadata,
    Column("target_id", String, ForeignKey("target_t.id"), primary_key=True),
    Column("cred_id", Integer, ForeignKey("credential_t.id"), primary_key=True)
)
