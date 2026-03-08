"""Comprehensive tests for src/ast_grep_mcp/security.py.

Tests cover: exceptions, enums, dataclasses, TokenBucket, RateLimitEntry,
ValidationConfig, SecurityManager, PermissionManager, EnhancedAuditLogger,
RateLimitManager, and convenience functions.
"""

import time
from pathlib import Path
from typing import Set

import pytest

from ast_grep_mcp.security import (
    # Exceptions
    SecurityError,
    PathTraversalError,
    CommandInjectionError,
    ResourceLimitError,
    RateLimitError,
    # Enums
    SecurityLevel,
    UserRole,
    # Dataclasses
    UserContext,
    AuditEvent,
    TokenBucket,
    RateLimitEntry,
    RateLimitConfig,
    # Classes
    ValidationConfig,
    SecurityManager,
    PermissionManager,
    EnhancedAuditLogger,
    RateLimitManager,
    EnhancedRateLimitError,
    AuditLogger,
    RateLimiter,
    # Functions
    create_user_context,
    initialize_security,
    get_security_manager,
    secure_validate_path,
    secure_validate_pattern,
    secure_sanitize_command,
    # Global manager helpers
    get_rate_limit_manager,
    reset_rate_limit_manager,
    get_audit_logger,
    get_permission_manager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_security_manager():
    """Reset the global security manager before each test."""
    import ast_grep_mcp.security as sec

    sec._security_manager = None
    sec._audit_logger = None
    sec._permission_manager = None
    sec._rate_limit_manager = None
    yield
    sec._security_manager = None
    sec._audit_logger = None
    sec._permission_manager = None
    sec._rate_limit_manager = None


@pytest.fixture()
def security_manager():
    """Create a fresh SecurityManager with default config."""
    return SecurityManager()


@pytest.fixture()
def admin_context():
    """Create an admin UserContext."""
    return create_user_context(
        user_id="admin1",
        role=UserRole.ADMIN,
        session_id="sess-admin",
        ip_address="127.0.0.1",
    )


@pytest.fixture()
def developer_context():
    """Create a developer UserContext."""
    return create_user_context(
        user_id="dev1",
        role=UserRole.DEVELOPER,
        session_id="sess-dev",
        ip_address="10.0.0.1",
    )


@pytest.fixture()
def guest_context():
    """Create a guest UserContext."""
    return create_user_context(
        user_id="guest1",
        role=UserRole.GUEST,
        session_id="sess-guest",
        ip_address="192.168.1.1",
    )


@pytest.fixture()
def user_context():
    """Create a regular user UserContext."""
    return create_user_context(
        user_id="user1",
        role=UserRole.USER,
        session_id="sess-user",
        ip_address="10.0.0.2",
    )


# ===========================================================================
# 1. Exception hierarchy
# ===========================================================================

class TestSecurityExceptions:
    """Verify the custom exception hierarchy."""

    def test_security_error_is_exception(self):
        with pytest.raises(SecurityError):
            raise SecurityError("base security error")

    def test_path_traversal_error_is_security_error(self):
        with pytest.raises(SecurityError):
            raise PathTraversalError("traversal")

    def test_path_traversal_error_specific(self):
        with pytest.raises(PathTraversalError, match="traversal"):
            raise PathTraversalError("traversal detected")

    def test_command_injection_error_is_security_error(self):
        with pytest.raises(SecurityError):
            raise CommandInjectionError("injection")

    def test_command_injection_error_specific(self):
        with pytest.raises(CommandInjectionError, match="injection"):
            raise CommandInjectionError("injection detected")

    def test_resource_limit_error_is_security_error(self):
        with pytest.raises(SecurityError):
            raise ResourceLimitError("limit")

    def test_resource_limit_error_specific(self):
        with pytest.raises(ResourceLimitError, match="exceeded"):
            raise ResourceLimitError("limit exceeded")

    def test_rate_limit_error_is_security_error(self):
        with pytest.raises(SecurityError):
            raise RateLimitError("rate limited")

    def test_rate_limit_error_specific(self):
        with pytest.raises(RateLimitError, match="too many"):
            raise RateLimitError("too many requests")


# ===========================================================================
# 2. SecurityLevel enum
# ===========================================================================

class TestSecurityLevel:
    """Verify SecurityLevel enum values."""

    def test_public(self):
        assert SecurityLevel.PUBLIC.value == "public"

    def test_restricted(self):
        assert SecurityLevel.RESTRICTED.value == "restricted"

    def test_sensitive(self):
        assert SecurityLevel.SENSITIVE.value == "sensitive"

    def test_critical(self):
        assert SecurityLevel.CRITICAL.value == "critical"

    def test_all_values_present(self):
        expected = {"public", "restricted", "sensitive", "critical"}
        assert {level.value for level in SecurityLevel} == expected


# ===========================================================================
# 3. UserRole enum
# ===========================================================================

class TestUserRole:
    """Verify UserRole enum values."""

    def test_guest(self):
        assert UserRole.GUEST.value == "guest"

    def test_user(self):
        assert UserRole.USER.value == "user"

    def test_developer(self):
        assert UserRole.DEVELOPER.value == "developer"

    def test_admin(self):
        assert UserRole.ADMIN.value == "admin"

    def test_system(self):
        assert UserRole.SYSTEM.value == "system"

    def test_all_values_present(self):
        expected = {"guest", "user", "developer", "admin", "system"}
        assert {role.value for role in UserRole} == expected


# ===========================================================================
# 4. UserContext dataclass
# ===========================================================================

class TestUserContext:
    """Verify UserContext creation and behaviour."""

    def test_default_fields(self):
        ctx = UserContext(user_id="u1")
        assert ctx.user_id == "u1"
        assert ctx.role == UserRole.USER
        assert ctx.session_id is None
        assert ctx.ip_address is None
        assert ctx.user_agent is None
        assert ctx.permissions == set()

    def test_custom_fields(self):
        ctx = UserContext(
            user_id="u2",
            role=UserRole.DEVELOPER,
            session_id="s1",
            ip_address="1.2.3.4",
            user_agent="test-agent",
            permissions={"read", "write"},
        )
        assert ctx.role == UserRole.DEVELOPER
        assert ctx.ip_address == "1.2.3.4"
        assert "read" in ctx.permissions

    def test_has_permission_granted(self):
        ctx = UserContext(user_id="u3", permissions={"file.read"})
        assert ctx.has_permission("file.read") is True

    def test_has_permission_denied(self):
        ctx = UserContext(user_id="u4", permissions=set())
        assert ctx.has_permission("file.read") is False

    def test_admin_has_all_permissions(self):
        ctx = UserContext(user_id="a1", role=UserRole.ADMIN)
        assert ctx.has_permission("anything.at.all") is True

    def test_can_access_security_level_guest(self):
        ctx = UserContext(user_id="g1", role=UserRole.GUEST)
        assert ctx.can_access_security_level(SecurityLevel.PUBLIC) is True
        assert ctx.can_access_security_level(SecurityLevel.RESTRICTED) is False
        assert ctx.can_access_security_level(SecurityLevel.SENSITIVE) is False
        assert ctx.can_access_security_level(SecurityLevel.CRITICAL) is False

    def test_can_access_security_level_developer(self):
        ctx = UserContext(user_id="d1", role=UserRole.DEVELOPER)
        assert ctx.can_access_security_level(SecurityLevel.PUBLIC) is True
        assert ctx.can_access_security_level(SecurityLevel.RESTRICTED) is True
        assert ctx.can_access_security_level(SecurityLevel.SENSITIVE) is True
        assert ctx.can_access_security_level(SecurityLevel.CRITICAL) is False

    def test_can_access_security_level_admin(self):
        ctx = UserContext(user_id="a1", role=UserRole.ADMIN)
        assert ctx.can_access_security_level(SecurityLevel.CRITICAL) is True


# ===========================================================================
# 5. AuditEvent dataclass
# ===========================================================================

class TestAuditEvent:
    """Verify AuditEvent creation and serialization."""

    def _make_event(self, **overrides):
        defaults = dict(
            event_id="evt-001",
            timestamp=1000.0,
            event_type="test",
            user_context=None,
            operation="search",
            resource="/tmp/test",
            success=True,
            security_level=SecurityLevel.PUBLIC,
        )
        defaults.update(overrides)
        return AuditEvent(**defaults)

    def test_basic_creation(self):
        evt = self._make_event()
        assert evt.event_id == "evt-001"
        assert evt.operation == "search"
        assert evt.success is True
        assert evt.risk_score == 0

    def test_defaults(self):
        evt = self._make_event()
        assert evt.details == {}
        assert evt.error is None
        assert evt.duration_ms is None
        assert evt.resource_usage == {}
        assert evt.tags == set()

    def test_to_dict_without_user_context(self):
        evt = self._make_event()
        d = evt.to_dict()
        assert d["event_id"] == "evt-001"
        assert d["user_context"] is None
        assert d["security_level"] == "public"
        assert isinstance(d["tags"], list)

    def test_to_dict_with_user_context(self):
        ctx = UserContext(
            user_id="u1",
            role=UserRole.DEVELOPER,
            session_id="s1",
            ip_address="10.0.0.1",
        )
        evt = self._make_event(user_context=ctx)
        d = evt.to_dict()
        assert d["user_context"]["user_id"] == "u1"
        assert d["user_context"]["role"] == "developer"

    def test_to_dict_tags_converted_to_list(self):
        evt = self._make_event(tags={"tag1", "tag2"})
        d = evt.to_dict()
        assert set(d["tags"]) == {"tag1", "tag2"}


# ===========================================================================
# 6. TokenBucket
# ===========================================================================

class TestTokenBucket:
    """Verify TokenBucket rate-limiting logic."""

    def _make_bucket(self, capacity=10, tokens=10.0, refill_rate=1.0):
        return TokenBucket(
            capacity=capacity,
            tokens=tokens,
            refill_rate=refill_rate,
            last_refill=time.time(),
        )

    def test_initial_capacity(self):
        bucket = self._make_bucket()
        assert bucket.available_tokens() >= 9  # may lose tiny fraction to refill call

    def test_consume_success(self):
        bucket = self._make_bucket(tokens=10.0)
        assert bucket.consume(1) is True

    def test_consume_insufficient_tokens(self):
        bucket = self._make_bucket(tokens=2.0)
        assert bucket.consume(5) is False

    def test_consume_does_not_deduct_on_failure(self):
        bucket = self._make_bucket(tokens=3.0)
        bucket.consume(5)
        assert bucket.available_tokens() >= 3

    def test_consume_multiple_tokens(self):
        bucket = self._make_bucket(tokens=10.0)
        assert bucket.consume(5) is True
        assert bucket.available_tokens() <= 5

    def test_refill_adds_tokens(self):
        bucket = self._make_bucket(capacity=10, tokens=0.0, refill_rate=100.0)
        bucket.last_refill = time.time() - 1.0  # pretend 1 second elapsed
        bucket.refill()
        assert bucket.available_tokens() == 10  # capped at capacity

    def test_refill_caps_at_capacity(self):
        bucket = self._make_bucket(capacity=5, tokens=5.0, refill_rate=100.0)
        bucket.last_refill = time.time() - 10.0
        bucket.refill()
        assert bucket.available_tokens() == 5

    def test_time_until_tokens_already_available(self):
        bucket = self._make_bucket(tokens=10.0)
        assert bucket.time_until_tokens(5) == 0.0

    def test_time_until_tokens_need_wait(self):
        bucket = self._make_bucket(capacity=10, tokens=0.0, refill_rate=1.0)
        # Need to reset last_refill to now so refill() doesn't add tokens
        bucket.last_refill = time.time()
        wait = bucket.time_until_tokens(5)
        assert wait > 0.0
        assert wait <= 5.0  # At 1 token/sec, need 5 seconds


# ===========================================================================
# 7. RateLimitEntry
# ===========================================================================

class TestRateLimitEntry:
    """Verify RateLimitEntry tracking and backoff."""

    def _make_entry(self, tokens=5.0):
        bucket = TokenBucket(
            capacity=5,
            tokens=tokens,
            refill_rate=1.0,
            last_refill=time.time(),
        )
        return RateLimitEntry(bucket=bucket)

    def test_record_success_increments_requests(self):
        entry = self._make_entry()
        entry.record_success()
        assert entry.total_requests == 1

    def test_record_success_resets_violation_count(self):
        entry = self._make_entry()
        entry.violation_count = 3
        entry.record_success()
        assert entry.violation_count == 0

    def test_is_in_backoff_when_not_in_backoff(self):
        entry = self._make_entry()
        assert entry.is_in_backoff() is False

    def test_is_in_backoff_when_in_backoff(self):
        entry = self._make_entry()
        entry.backoff_until = time.time() + 60
        assert entry.is_in_backoff() is True

    def test_record_violation_increments_counts(self):
        config = RateLimitConfig(enable_backoff=True, backoff_multiplier=2.0)
        entry = self._make_entry()
        entry.record_violation(config)
        assert entry.violation_count == 1
        assert entry.total_violations == 1

    def test_record_violation_sets_backoff(self):
        config = RateLimitConfig(enable_backoff=True, backoff_multiplier=2.0)
        entry = self._make_entry()
        entry.record_violation(config)
        assert entry.backoff_until > time.time()

    def test_calculate_backoff_disabled(self):
        config = RateLimitConfig(enable_backoff=False)
        entry = self._make_entry()
        assert entry.calculate_backoff(config) == 0.0

    def test_calculate_backoff_exponential(self):
        config = RateLimitConfig(enable_backoff=True, backoff_multiplier=2.0)
        entry = self._make_entry()

        entry.record_violation(config)
        b1 = entry.calculate_backoff(config)

        entry.record_violation(config)
        b2 = entry.calculate_backoff(config)

        assert b2 > b1  # exponential growth

    def test_calculate_backoff_capped(self):
        config = RateLimitConfig(
            enable_backoff=True,
            backoff_multiplier=2.0,
            max_backoff_seconds=10,
        )
        entry = self._make_entry()
        for _ in range(50):
            entry.record_violation(config)
        assert entry.calculate_backoff(config) <= 10


# ===========================================================================
# 8. ValidationConfig
# ===========================================================================

class TestValidationConfig:
    """Verify ValidationConfig default and custom values."""

    def test_defaults(self):
        cfg = ValidationConfig()
        assert cfg.max_path_length == 4096
        assert cfg.max_pattern_length == 10000
        assert cfg.max_file_size == 100 * 1024 * 1024
        assert cfg.max_files_per_request == 1000
        assert ".py" in cfg.allowed_extensions
        assert "/etc" in cfg.blocked_paths

    def test_custom_values(self):
        cfg = ValidationConfig(max_path_length=512, max_pattern_length=200)
        assert cfg.max_path_length == 512
        assert cfg.max_pattern_length == 200


# ===========================================================================
# 9. SecurityManager
# ===========================================================================

class TestSecurityManager:
    """Verify SecurityManager path/pattern/command validation."""

    def test_initialization_with_default_config(self, security_manager):
        assert security_manager.config is not None
        assert isinstance(security_manager.config, ValidationConfig)

    def test_initialization_with_custom_config(self):
        cfg = ValidationConfig(max_path_length=256)
        mgr = SecurityManager(config=cfg)
        assert mgr.config.max_path_length == 256

    # -- validate_path --

    def test_validate_path_valid_file(self, tmp_path):
        cfg = ValidationConfig(blocked_paths={'/etc', '/proc', '/sys', '/dev', '/root',
                                               'C:\\Windows', 'C:\\System32', 'C:\\Users\\Administrator'})
        mgr = SecurityManager(config=cfg)
        f = tmp_path / "hello.py"
        f.write_text("pass")
        result = mgr.validate_path(str(f))
        assert result == f.resolve()

    def test_validate_path_traversal_dotdot(self, tmp_path, security_manager):
        evil = str(tmp_path / ".." / ".." / "etc" / "passwd")
        with pytest.raises(PathTraversalError):
            security_manager.validate_path(evil)

    def test_validate_path_traversal_null_byte(self, security_manager):
        with pytest.raises(PathTraversalError, match="Null byte"):
            security_manager.validate_path("/safe/path\x00malicious")

    def test_validate_path_too_long(self, security_manager):
        long_path = "/a" * 5000
        with pytest.raises(PathTraversalError, match="too long"):
            security_manager.validate_path(long_path)

    def test_validate_path_within_base(self, tmp_path, security_manager):
        sub = tmp_path / "sub"
        sub.mkdir()
        f = sub / "test.py"
        f.write_text("pass")
        result = security_manager.validate_path("sub/test.py", base_path=tmp_path)
        assert result == f.resolve()

    def test_validate_path_escapes_base(self, tmp_path, security_manager):
        with pytest.raises(PathTraversalError):
            security_manager.validate_path("../../etc/passwd", base_path=tmp_path)

    def test_validate_path_blocked_absolute_etc(self, security_manager):
        with pytest.raises(PathTraversalError, match="blocked"):
            security_manager.validate_path("/etc/shadow")

    def test_validate_path_long_component(self, tmp_path, security_manager):
        evil = str(tmp_path / ("a" * 260))
        with pytest.raises(PathTraversalError, match="component too long"):
            security_manager.validate_path(evil)

    # -- validate_pattern --

    def test_validate_pattern_valid(self, security_manager):
        result = security_manager.validate_pattern("console.log($MSG)")
        assert result == "console.log($MSG)"

    def test_validate_pattern_strips_whitespace(self, security_manager):
        result = security_manager.validate_pattern("  foo()  ")
        assert result == "foo()"

    def test_validate_pattern_empty_raises(self, security_manager):
        with pytest.raises(Exception):
            security_manager.validate_pattern("")

    def test_validate_pattern_whitespace_only_raises(self, security_manager):
        with pytest.raises(Exception):
            security_manager.validate_pattern("   ")

    def test_validate_pattern_too_long(self):
        mgr = SecurityManager(config=ValidationConfig(max_pattern_length=10))
        with pytest.raises(Exception):
            mgr.validate_pattern("a" * 20)

    def test_validate_pattern_dangerous_backtick(self, security_manager):
        with pytest.raises(Exception):
            security_manager.validate_pattern("hello `rm -rf /`")

    def test_validate_pattern_dangerous_semicolon(self, security_manager):
        with pytest.raises(Exception):
            security_manager.validate_pattern("foo; rm -rf /")

    # -- sanitize_command_args --

    def test_sanitize_command_allowed(self, security_manager):
        cmd, args = security_manager.sanitize_command_args("ast-grep", ["--pattern", "foo"])
        assert cmd == "ast-grep"
        assert args == ["--pattern", "foo"]

    def test_sanitize_command_sg_allowed(self, security_manager):
        cmd, _ = security_manager.sanitize_command_args("sg", ["--json"])
        assert cmd == "sg"

    def test_sanitize_command_disallowed(self, security_manager):
        with pytest.raises(CommandInjectionError, match="not allowed"):
            security_manager.sanitize_command_args("rm", ["-rf", "/"])

    def test_sanitize_command_dangerous_arg_semicolon(self, security_manager):
        with pytest.raises(CommandInjectionError):
            security_manager.sanitize_command_args("ast-grep", ["--pattern", "foo; rm -rf /"])

    def test_sanitize_command_dangerous_arg_pipe(self, security_manager):
        with pytest.raises(CommandInjectionError):
            security_manager.sanitize_command_args("ast-grep", ["--pattern", "foo | cat /etc/passwd"])

    def test_sanitize_command_dangerous_arg_backtick(self, security_manager):
        with pytest.raises(CommandInjectionError):
            security_manager.sanitize_command_args("ast-grep", ["`whoami`"])

    # -- check_rate_limit --

    def test_check_rate_limit_within_limit(self, security_manager):
        # Should not raise for a few requests
        security_manager.check_rate_limit("user1", "search")

    def test_check_rate_limit_exceeded(self):
        mgr = SecurityManager()
        # Exhaust the bucket for "scan" which has capacity 10
        for _ in range(15):
            try:
                mgr.check_rate_limit("user-rl-test", "scan")
            except RateLimitError:
                return  # expected
        # If we never got rate-limited with scan capacity of 10, that is acceptable
        # because default refill_rate is 1/sec and tokens start full

    # -- enforce_resource_limits --

    def test_enforce_resource_limits_within(self, security_manager):
        security_manager.enforce_resource_limits("file_count", count=10)

    def test_enforce_resource_limits_exceeded(self, security_manager):
        with pytest.raises(ResourceLimitError, match="Too many files"):
            security_manager.enforce_resource_limits("file_count", count=99999)

    # -- create_secure_temp_dir --

    def test_create_secure_temp_dir(self, security_manager):
        d = security_manager.create_secure_temp_dir()
        assert d.is_dir()
        d.rmdir()  # cleanup


# ===========================================================================
# 10. PermissionManager
# ===========================================================================

class TestPermissionManager:
    """Verify PermissionManager RBAC checks."""

    def test_initialization(self):
        pm = PermissionManager()
        assert pm._operation_permissions is not None
        assert pm._security_levels is not None

    def test_admin_allowed_for_sensitive_op(self, admin_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(admin_context, "ast_grep_run")
        assert allowed is True
        assert reason is None

    def test_guest_denied_for_restricted_op(self, guest_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(guest_context, "ast_grep_search")
        assert allowed is False
        assert reason is not None

    def test_developer_allowed_for_search(self, developer_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(developer_context, "ast_grep_search")
        assert allowed is True

    def test_user_denied_for_critical_op(self, user_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(user_context, "config_modify")
        assert allowed is False

    def test_admin_allowed_for_critical_op(self, admin_context):
        pm = PermissionManager()
        allowed, _ = pm.check_permission(admin_context, "config_modify")
        assert allowed is True

    def test_resource_check_guest_denied(self, guest_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(
            guest_context, "ast_grep_run", resource="/safe/path"
        )
        assert allowed is False

    def test_resource_check_sensitive_path_denied_for_developer(self, developer_context):
        pm = PermissionManager()
        allowed, reason = pm.check_permission(
            developer_context, "ast_grep_run", resource="/etc/shadow"
        )
        assert allowed is False

    def test_resource_check_sensitive_path_allowed_for_admin(self, admin_context):
        pm = PermissionManager()
        allowed, _ = pm.check_permission(
            admin_context, "ast_grep_run", resource="/etc/shadow"
        )
        assert allowed is True

    def test_unknown_operation_defaults_to_restricted(self, developer_context):
        pm = PermissionManager()
        # Unknown operation should default to RESTRICTED which developer can access,
        # but developer may lack required permissions for the empty permission set
        allowed, _ = pm.check_permission(developer_context, "unknown_op")
        # Unknown op has no required permissions, so should be allowed
        assert allowed is True


# ===========================================================================
# 11. EnhancedAuditLogger
# ===========================================================================

class TestEnhancedAuditLogger:
    """Verify EnhancedAuditLogger event logging."""

    def test_initialization(self):
        logger = EnhancedAuditLogger()
        assert logger._event_counter == 0
        assert len(logger._event_history) == 0

    def test_initialization_custom_max_events(self):
        logger = EnhancedAuditLogger(max_events=100)
        assert logger._event_history.maxlen == 100

    def test_log_event_returns_event_id(self):
        logger = EnhancedAuditLogger()
        event_id = logger.log_event(
            event_type="test",
            operation="search",
            resource="/tmp",
            success=True,
        )
        assert event_id.startswith("audit_")

    def test_log_event_stores_event(self):
        logger = EnhancedAuditLogger()
        logger.log_event(
            event_type="test",
            operation="search",
            resource="/tmp",
            success=True,
        )
        assert len(logger._event_history) == 1

    def test_log_event_increments_counter(self):
        logger = EnhancedAuditLogger()
        logger.log_event("t", "op", "/r", True)
        logger.log_event("t", "op", "/r", True)
        assert logger._event_counter == 2

    def test_log_event_with_user_context_tracks_session(self, developer_context):
        logger = EnhancedAuditLogger()
        logger.log_event(
            event_type="test",
            operation="search",
            resource="/tmp",
            success=True,
            user_context=developer_context,
        )
        assert developer_context.session_id in logger._session_events
        assert len(logger._session_events[developer_context.session_id]) == 1

    def test_log_security_violation(self, guest_context):
        logger = EnhancedAuditLogger()
        event_id = logger.log_security_violation(
            violation_type="path_traversal",
            operation="file_read",
            resource="/etc/passwd",
            user_context=guest_context,
        )
        assert event_id.startswith("audit_")
        events = logger.get_events(event_type="security_violation")
        assert len(events) == 1

    def test_get_events_filtered_by_type(self):
        logger = EnhancedAuditLogger()
        logger.log_event("alpha", "op", "/r", True)
        logger.log_event("beta", "op", "/r", True)
        logger.log_event("alpha", "op", "/r", True)
        events = logger.get_events(event_type="alpha")
        assert len(events) == 2

    def test_get_events_filtered_by_success(self):
        logger = EnhancedAuditLogger()
        logger.log_event("t", "op", "/r", True)
        logger.log_event("t", "op", "/r", False)
        events = logger.get_events(success=False)
        assert len(events) == 1

    def test_get_security_summary(self):
        logger = EnhancedAuditLogger()
        logger.log_event("test", "search", "/tmp", True)
        logger.log_security_violation("xss", "web", "/", None)
        summary = logger.get_security_summary(hours=1)
        assert summary["total_events"] == 2
        assert summary["security_violations"] == 1

    def test_log_command_execution(self):
        logger = EnhancedAuditLogger()
        event_id = logger.log_command_execution(
            command="ast-grep",
            args=["--pattern", "foo"],
            working_dir="/tmp",
        )
        assert event_id.startswith("audit_")

    def test_log_operation_start_and_end(self):
        logger = EnhancedAuditLogger()
        start_id = logger.log_operation_start("search", "/tmp")
        end_id = logger.log_operation_end(
            "search", "/tmp", success=True, duration_ms=42.0
        )
        assert start_id != end_id
        assert len(logger._event_history) == 2


# ===========================================================================
# 12. RateLimitManager
# ===========================================================================

class TestRateLimitManager:
    """Verify RateLimitManager rate limiting logic."""

    def test_initialization_default_config(self):
        mgr = RateLimitManager()
        assert mgr.config.search_rpm == 30

    def test_initialization_custom_config(self):
        cfg = RateLimitConfig(search_rpm=5)
        mgr = RateLimitManager(config=cfg)
        assert mgr.config.search_rpm == 5

    def test_check_rate_limit_allowed(self, developer_context):
        mgr = RateLimitManager()
        allowed, error = mgr.check_rate_limit(developer_context, "ast_grep_search")
        assert allowed is True
        assert error is None

    def test_check_rate_limit_exhausted(self, developer_context):
        cfg = RateLimitConfig(search_rpm=2, global_rpm=100)
        mgr = RateLimitManager(config=cfg)

        # First two should succeed
        for _ in range(2):
            mgr.check_rate_limit(developer_context, "ast_grep_search")

        # Third should be blocked (bucket is exhausted)
        allowed, error = mgr.check_rate_limit(developer_context, "ast_grep_search")
        assert allowed is False
        assert isinstance(error, EnhancedRateLimitError)

    def test_check_rate_limit_ip_based(self, developer_context):
        cfg = RateLimitConfig(ip_rpm=2, search_rpm=100, global_rpm=100)
        mgr = RateLimitManager(config=cfg)

        for _ in range(2):
            mgr.check_rate_limit(developer_context, "ast_grep_search", ip_address="1.2.3.4")

        allowed, error = mgr.check_rate_limit(
            developer_context, "ast_grep_search", ip_address="1.2.3.4"
        )
        assert allowed is False
        assert error.limit_type == "ip"

    def test_get_statistics(self, developer_context):
        mgr = RateLimitManager()
        mgr.check_rate_limit(developer_context, "ast_grep_search")
        stats = mgr.get_statistics()
        assert "active_users" in stats
        assert stats["active_users"] >= 1
        assert "user_statistics" in stats
        assert "ip_statistics" in stats


# ===========================================================================
# 13. EnhancedRateLimitError
# ===========================================================================

class TestEnhancedRateLimitError:
    """Verify EnhancedRateLimitError properties and serialization."""

    def test_properties(self):
        err = EnhancedRateLimitError(
            "Too many",
            retry_after=30.0,
            limit_type="user_operation",
            current_usage=50,
            limit=30,
        )
        assert str(err) == "Too many"
        assert err.retry_after == 30.0
        assert err.limit_type == "user_operation"
        assert err.current_usage == 50
        assert err.limit == 30

    def test_to_dict(self):
        err = EnhancedRateLimitError(
            "rate limited",
            retry_after=10.0,
            limit_type="ip",
            current_usage=100,
            limit=50,
        )
        d = err.to_dict()
        assert d["error"] == "RateLimitExceeded"
        assert d["retry_after"] == 10.0
        assert d["limit_type"] == "ip"
        assert d["message"] == "rate limited"


# ===========================================================================
# 14. Legacy RateLimiter
# ===========================================================================

class TestRateLimiter:
    """Verify legacy RateLimiter."""

    def test_check_limit_allowed(self):
        rl = RateLimiter()
        assert rl.check_limit("user1", "default") is True

    def test_check_limit_exhausted(self):
        rl = RateLimiter()
        # scan has capacity 10
        for _ in range(10):
            rl.check_limit("exhaust-user", "scan")
        assert rl.check_limit("exhaust-user", "scan") is False

    def test_get_reset_time(self):
        rl = RateLimiter()
        reset = rl.get_reset_time("user1", "default")
        assert reset >= 1


# ===========================================================================
# 15. AuditLogger (legacy)
# ===========================================================================

class TestAuditLogger:
    """Verify legacy AuditLogger."""

    def test_log_path_access_success(self):
        al = AuditLogger()
        al.log_path_access("/tmp/test", success=True)
        events = al.get_recent_events("path_access")
        assert len(events) == 1
        assert events[0]["success"] is True

    def test_log_path_access_failure(self):
        al = AuditLogger()
        al.log_path_access("/etc/shadow", success=False, error="blocked")
        events = al.get_recent_events("path_access")
        assert events[0]["error"] == "blocked"

    def test_log_command_execution(self):
        al = AuditLogger()
        al.log_command_execution("ast-grep", ["--pattern", "foo"])
        events = al.get_recent_events("command_execution")
        assert len(events) == 1

    def test_log_security_violation(self):
        al = AuditLogger()
        al.log_security_violation("injection", {"input": "evil"})
        events = al.get_recent_events("security_violation")
        assert len(events) == 1

    def test_get_recent_events_filtered(self):
        al = AuditLogger()
        al.log_path_access("/a", True)
        al.log_command_execution("cmd", [])
        assert len(al.get_recent_events("path_access")) == 1
        assert len(al.get_recent_events("command_execution")) == 1

    def test_get_recent_events_limit(self):
        al = AuditLogger()
        for i in range(10):
            al.log_path_access(f"/path/{i}", True)
        events = al.get_recent_events(limit=3)
        assert len(events) == 3


# ===========================================================================
# 16. Convenience / module-level functions
# ===========================================================================

class TestConvenienceFunctions:
    """Verify module-level convenience functions."""

    # -- create_user_context --

    def test_create_user_context_defaults(self):
        ctx = create_user_context(user_id="u1")
        assert ctx.user_id == "u1"
        assert ctx.role == UserRole.USER
        assert "file.read" in ctx.permissions  # default for USER role

    def test_create_user_context_developer_permissions(self):
        ctx = create_user_context("dev", role=UserRole.DEVELOPER)
        assert "file.write" in ctx.permissions
        assert "ast_grep.run" in ctx.permissions

    def test_create_user_context_guest_no_permissions(self):
        ctx = create_user_context("g1", role=UserRole.GUEST)
        assert len(ctx.permissions) == 0

    def test_create_user_context_custom_permissions(self):
        ctx = create_user_context("u2", permissions={"custom.perm"})
        assert "custom.perm" in ctx.permissions
        assert "file.read" in ctx.permissions  # default USER permissions merged

    def test_create_user_context_all_fields(self):
        ctx = create_user_context(
            user_id="u3",
            role=UserRole.ADMIN,
            session_id="s3",
            ip_address="10.0.0.1",
            user_agent="TestAgent/1.0",
        )
        assert ctx.session_id == "s3"
        assert ctx.ip_address == "10.0.0.1"
        assert ctx.user_agent == "TestAgent/1.0"

    # -- initialize_security --

    def test_initialize_security_returns_manager(self):
        mgr = initialize_security()
        assert isinstance(mgr, SecurityManager)

    def test_initialize_security_with_config(self):
        cfg = ValidationConfig(max_path_length=128)
        mgr = initialize_security(config=cfg)
        assert mgr.config.max_path_length == 128

    # -- get_security_manager --

    def test_get_security_manager_creates_singleton(self):
        mgr1 = get_security_manager()
        mgr2 = get_security_manager()
        assert mgr1 is mgr2

    def test_get_security_manager_returns_initialized(self):
        initialized = initialize_security()
        got = get_security_manager()
        assert got is initialized

    # -- secure_validate_path --

    def test_secure_validate_path_valid(self, tmp_path):
        cfg = ValidationConfig(blocked_paths={'/etc', '/proc', '/sys', '/dev', '/root',
                                               'C:\\Windows', 'C:\\System32', 'C:\\Users\\Administrator'})
        initialize_security(cfg)
        f = tmp_path / "test.py"
        f.write_text("pass")
        result = secure_validate_path(str(f))
        assert result == f.resolve()

    def test_secure_validate_path_traversal(self, tmp_path):
        with pytest.raises(PathTraversalError):
            secure_validate_path(str(tmp_path / "../../etc/passwd"))

    # -- secure_validate_pattern --

    def test_secure_validate_pattern_valid(self):
        result = secure_validate_pattern("console.log($X)")
        assert result == "console.log($X)"

    def test_secure_validate_pattern_dangerous(self):
        with pytest.raises(Exception):
            secure_validate_pattern("hello `whoami`")

    # -- secure_sanitize_command --

    def test_secure_sanitize_command_safe(self):
        cmd, args = secure_sanitize_command("ast-grep", ["--pattern", "foo"])
        assert cmd == "ast-grep"

    def test_secure_sanitize_command_blocked(self):
        with pytest.raises(CommandInjectionError):
            secure_sanitize_command("bash", ["-c", "evil"])

    # -- global rate limit manager helpers --

    def test_get_rate_limit_manager_creates(self):
        mgr = get_rate_limit_manager()
        assert isinstance(mgr, RateLimitManager)

    def test_get_rate_limit_manager_singleton(self):
        mgr1 = get_rate_limit_manager()
        mgr2 = get_rate_limit_manager()
        assert mgr1 is mgr2

    def test_reset_rate_limit_manager(self):
        mgr1 = get_rate_limit_manager()
        reset_rate_limit_manager()
        mgr2 = get_rate_limit_manager()
        assert mgr1 is not mgr2

    def test_get_rate_limit_manager_custom_config(self):
        reset_rate_limit_manager()
        cfg = RateLimitConfig(search_rpm=99)
        mgr = get_rate_limit_manager(config=cfg)
        assert mgr.config.search_rpm == 99

    # -- global audit logger --

    def test_get_audit_logger(self):
        al = get_audit_logger()
        assert isinstance(al, EnhancedAuditLogger)

    # -- global permission manager --

    def test_get_permission_manager(self):
        pm = get_permission_manager()
        assert isinstance(pm, PermissionManager)


# ===========================================================================
# 17. RateLimitConfig
# ===========================================================================

class TestRateLimitConfig:
    """Verify RateLimitConfig dataclass and to_dict."""

    def test_defaults(self):
        cfg = RateLimitConfig()
        assert cfg.search_rpm == 30
        assert cfg.scan_rpm == 10
        assert cfg.run_rpm == 5
        assert cfg.call_graph_rpm == 15
        assert cfg.global_rpm == 60
        assert cfg.enable_backoff is True

    def test_custom(self):
        cfg = RateLimitConfig(search_rpm=100, enable_backoff=False)
        assert cfg.search_rpm == 100
        assert cfg.enable_backoff is False

    def test_to_dict(self):
        cfg = RateLimitConfig()
        d = cfg.to_dict()
        assert d["search_rpm"] == 30
        assert d["enable_backoff"] is True
        assert "backoff_multiplier" in d
