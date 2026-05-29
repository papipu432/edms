import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.group import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


# Keep the old RoleName enum for backward compatibility with existing code
class RoleName(str, enum.Enum):
    admin = "admin"
    reviewer = "reviewer"
    editor = "editor"
    annotator = "annotator"
    approver = "approver"


# ── Users ────────────────────────────────────────────────────────────────────


class UserStatus(str, enum.Enum):
    active = "active"
    resigned = "resigned"
    terminated = "terminated"
    mia = "mia"  # Missing In Action
    on_leave = "on_leave"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(256), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), default=UserStatus.active, nullable=False
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status_changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ldap: Mapped[bool] = mapped_column(Boolean, default=False)
    ldap_dn: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True
    )

    # Relations
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserRole.user_id",
        lazy="selectin",
    )
    folder_assignments: Mapped[list["FolderAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    org_assignments: Mapped[list["OrgUserAssignment"]] = relationship(
        back_populates="user", foreign_keys="OrgUserAssignment.user_id", lazy="selectin"
    )
    personal_grades: Mapped[list["OrgUserGrade"]] = relationship(
        back_populates="user", foreign_keys="OrgUserGrade.user_id", lazy="selectin"
    )

    @property
    def roles(self) -> list["Role"]:
        """Return list of Role objects for backward compatibility."""
        return [ur.role for ur in self.user_roles if ur.role is not None]

    @property
    def role_codes(self) -> list[str]:
        """Return list of role code strings."""
        return [ur.role.code for ur in self.user_roles if ur.role is not None]

    @property
    def permissions(self) -> list[str]:
        """Return list of 'resource:action' permission strings."""
        perms: set[str] = set()
        for ur in self.user_roles:
            if ur.role is not None:
                for rp in ur.role.permissions:
                    if rp.permission is not None:
                        perms.add(f"{rp.permission.resource}:{rp.permission.action}")
        return list(perms)


# ── RBAC ─────────────────────────────────────────────────────────────────────


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="role", lazy="selectin"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", lazy="selectin"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    granted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(
        back_populates="user_roles", foreign_keys=[user_id]
    )
    role: Mapped["Role"] = relationship(back_populates="user_roles", lazy="selectin")


# ── Org Structure ─────────────────────────────────────────────────────────────


class OrgUnitType(Base):
    __tablename__ = "org_unit_types"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    units: Mapped[list["OrgUnit"]] = relationship(back_populates="unit_type")


class OrgUnit(Base):
    __tablename__ = "org_units"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(64))
    type_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_unit_types.id")
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_units.id")
    )
    head_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now()
    )

    unit_type: Mapped["OrgUnitType | None"] = relationship(back_populates="units")
    parent: Mapped["OrgUnit | None"] = relationship(
        remote_side="OrgUnit.id", foreign_keys=[parent_id]
    )
    head_user: Mapped["User | None"] = relationship(foreign_keys=[head_user_id])
    positions: Mapped[list["OrgPosition"]] = relationship(back_populates="unit")
    assignments: Mapped[list["OrgUserAssignment"]] = relationship(back_populates="unit")


class OrgGrade(Base):
    __tablename__ = "org_grades"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    grade_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    grade_name: Mapped[str] = mapped_column(String(128), nullable=False)
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False)
    grade_category: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    min_salary: Mapped[float | None] = mapped_column(Float)
    max_salary: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    positions: Mapped[list["OrgPosition"]] = relationship(back_populates="grade")
    user_grades: Mapped[list["OrgUserGrade"]] = relationship(back_populates="grade")


class OrgPosition(Base):
    __tablename__ = "org_positions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("org_units.id"), nullable=False
    )
    position_code: Mapped[str] = mapped_column(String(32), nullable=False)
    position_name: Mapped[str] = mapped_column(String(256), nullable=False)
    grade_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_grades.id")
    )
    is_head: Mapped[bool] = mapped_column(Boolean, default=False)
    max_occupants: Mapped[int] = mapped_column(Integer, default=1)
    current_occupants: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    unit: Mapped["OrgUnit"] = relationship(back_populates="positions")
    grade: Mapped["OrgGrade | None"] = relationship(back_populates="positions")
    assignments: Mapped[list["OrgUserAssignment"]] = relationship(
        back_populates="position"
    )


class OrgUserGrade(Base):
    __tablename__ = "org_user_grades"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    grade_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("org_grades.id"), nullable=False
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(
        back_populates="personal_grades", foreign_keys=[user_id]
    )
    grade: Mapped["OrgGrade"] = relationship(back_populates="user_grades")


class OrgUserAssignment(Base):
    __tablename__ = "org_user_assignments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    position_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("org_positions.id"), nullable=False
    )
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("org_units.id"), nullable=False
    )
    assignment_type: Mapped[str] = mapped_column(String(32), default="primary")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(
        back_populates="org_assignments", foreign_keys=[user_id]
    )
    position: Mapped["OrgPosition"] = relationship(back_populates="assignments")
    unit: Mapped["OrgUnit"] = relationship(back_populates="assignments")


# ── Change Audit ──────────────────────────────────────────────────────────────


class OrgChangeHistory(Base):
    __tablename__ = "org_change_history"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    change_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    changer: Mapped["User | None"] = relationship(foreign_keys=[changed_by])


# ── LDAP Config ───────────────────────────────────────────────────────────────


class LdapConfig(Base):
    __tablename__ = "ldap_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    server_url: Mapped[str] = mapped_column(String(256), nullable=False)
    server_port: Mapped[int] = mapped_column(Integer, default=389)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    connect_timeout: Mapped[int] = mapped_column(Integer, default=10)

    bind_dn: Mapped[str | None] = mapped_column(String(512))
    bind_password: Mapped[str | None] = mapped_column(String(512))
    base_dn: Mapped[str] = mapped_column(String(512), nullable=False)

    user_search_filter: Mapped[str] = mapped_column(
        String(256), default="(objectClass=person)"
    )
    user_search_base: Mapped[str | None] = mapped_column(String(512))
    group_search_filter: Mapped[str] = mapped_column(
        String(256), default="(objectClass=groupOfNames)"
    )
    group_search_base: Mapped[str | None] = mapped_column(String(512))

    attr_username: Mapped[str] = mapped_column(String(64), default="uid")
    attr_email: Mapped[str] = mapped_column(String(64), default="mail")
    attr_display_name: Mapped[str] = mapped_column(String(64), default="cn")
    attr_first_name: Mapped[str] = mapped_column(String(64), default="givenName")
    attr_last_name: Mapped[str] = mapped_column(String(64), default="sn")
    attr_department: Mapped[str] = mapped_column(
        String(64), default="departmentNumber"
    )
    attr_title: Mapped[str] = mapped_column(String(64), default="title")
    attr_member_of: Mapped[str] = mapped_column(String(64), default="memberOf")

    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_schedule: Mapped[str | None] = mapped_column(String(64))
    sync_create_users: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_update_users: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_disable_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    default_role: Mapped[str] = mapped_column(String(64), default="viewer")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now()
    )

    group_role_mappings: Mapped[list["LdapGroupRole"]] = relationship(
        back_populates="config", cascade="all, delete-orphan"
    )
    sync_logs: Mapped[list["LdapSyncLog"]] = relationship(
        back_populates="config", cascade="all, delete-orphan"
    )


class LdapGroupRole(Base):
    __tablename__ = "ldap_group_roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ldap_configs.id", ondelete="CASCADE"), nullable=False
    )
    ldap_group_dn: Mapped[str] = mapped_column(String(512), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    config: Mapped["LdapConfig"] = relationship(back_populates="group_role_mappings")


class LdapSyncLog(Base):
    __tablename__ = "ldap_sync_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    config_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ldap_configs.id")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="running")
    users_found: Mapped[int] = mapped_column(Integer, default=0)
    users_created: Mapped[int] = mapped_column(Integer, default=0)
    users_updated: Mapped[int] = mapped_column(Integer, default=0)
    users_disabled: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)

    config: Mapped["LdapConfig"] = relationship(back_populates="sync_logs")


# ── FolderAssignment (backward compat) ────────────────────────────────────────


class FolderAssignment(Base):
    __tablename__ = "folder_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False)
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="folder_assignments")
    role: Mapped["Role"] = relationship(lazy="selectin")
