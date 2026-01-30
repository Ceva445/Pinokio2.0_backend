from fastapi import Depends, HTTPException, status
from routers.auth import get_current_user
from models.db_user import UserRole

def require_admin(
    current_user: dict = Depends(get_current_user())
):
    if current_user["role"] != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins only"
        )
    return current_user
