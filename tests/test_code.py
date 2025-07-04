#!/usr/bin/env python3
"""Test Python file with various issues that our rules should catch."""

# This should trigger python-no-percent-formatting
message = "Hello %s" % name

# This should trigger python-no-bare-except
try:
    risky_operation()
except:
    pass

# This should trigger python-no-print-statements
print("Debug message")

# This should trigger python-no-mutable-defaults
def bad_function(items=[]):
    items.append("new item")
    return items

# This should trigger python-string-comparison
if name is "admin":
    access_granted = True

# This should trigger python-no-deprecated-assert
assert user_valid

# Some good code
def good_function():
    """This function follows best practices."""
    try:
        result = safe_operation()
        return result
    except ValueError as e:
        logger.error(f"Operation failed: {e}")
        raise