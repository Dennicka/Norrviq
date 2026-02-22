from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db import Base


class ProjectExecutionProfile(Base):
    __tablename__ = "project_execution_profiles"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, unique=True)
    speed_profile_id = Column(Integer, ForeignKey("speed_profiles.id"), nullable=True)
    apply_scope = Column(String(32), nullable=False, server_default="PROJECT")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="execution_profile")
    speed_profile = relationship("SpeedProfile")
