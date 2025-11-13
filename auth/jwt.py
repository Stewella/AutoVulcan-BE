from typing import Any, Dict

# Minimal stub for authentication dependency
# In production, validate JWT from Authorization header

def get_current_user() -> Dict[str, Any]:
    # return a dummy user; extend with actual JWT verification
    return {"id": "demo-user", "role": "tester"}