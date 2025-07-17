from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from typing import Optional
import httpx
from datetime import timedelta
import secrets
import logging

from core.config import settings
from core.database import get_async_session
from core.security import create_access_token, get_current_user
from schemas import User
from sqlmodel import select, and_
from models.user import User as UserModel, Account

router = APIRouter()
logger = logging.getLogger(__name__)

# Store temporary state for OAuth flow
oauth_states = {}


@router.get("/github")
async def github_login(redirect_uri: Optional[str] = None):
    """Initiate GitHub OAuth flow"""
    state = secrets.token_urlsafe(32)
    oauth_states[state] = redirect_uri or settings.frontend_url

    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope=read:user user:email repo"
        f"&state={state}"
    )

    return RedirectResponse(url=github_auth_url)


@router.get("/github/callback")
async def github_callback(code: str, state: str):
    """Handle GitHub OAuth callback"""
    # Verify state
    redirect_uri = oauth_states.pop(state, None)
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="Invalid state")

    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                },
            )
            token_data = token_response.json()

            if "error" in token_data:
                raise HTTPException(
                    status_code=400, detail=token_data["error_description"]
                )

            access_token = token_data["access_token"]

            # Get user info from GitHub
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            github_user = user_response.json()

            # Get user email if not public
            if not github_user.get("email"):
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                emails = email_response.json()
                primary_email = next((e["email"] for e in emails if e["primary"]), None)
                github_user["email"] = primary_email

        # Create or update user in database
        async with get_async_session() as session:
            # Try to find existing user by github_id
            existing_user_result = await session.execute(
                select(UserModel).where(UserModel.github_id == str(github_user["id"]))
            )
            user = existing_user_result.scalar_one_or_none()
            
            if user:
                # Update existing user
                user.email = github_user.get("email")
                user.name = github_user.get("name")
                user.image = github_user.get("avatar_url")
                session.add(user)
            else:
                # Create new user
                user = UserModel(
                    email=github_user.get("email"),
                    name=github_user.get("name"),
                    github_id=str(github_user["id"]),
                    image=github_user.get("avatar_url"),
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)

            # Update or create account record
            existing_account_result = await session.execute(
                select(Account).where(
                    and_(
                        Account.provider == "github",
                        Account.provider_account_id == str(github_user["id"])
                    )
                )
            )
            account = existing_account_result.scalar_one_or_none()
            
            if account:
                # Update existing account
                account.access_token = access_token
                account.token_type = "bearer"
                account.scope = token_data.get("scope")
                session.add(account)
            else:
                # Create new account
                account = Account(
                    user_id=user.id,
                    type="oauth",
                    provider="github",
                    provider_account_id=str(github_user["id"]),
                    access_token=access_token,
                    token_type="bearer",
                    scope=token_data.get("scope"),
                )
                session.add(account)
            
            await session.commit()

        # Create JWT token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        jwt_token = create_access_token(
            data={"sub": user.id}, expires_delta=access_token_expires
        )

        # Redirect to frontend with token
        return RedirectResponse(url=f"{redirect_uri}?token={jwt_token}")

    except Exception as e:
        logger.error(f"GitHub OAuth error: {str(e)}")
        return RedirectResponse(url=f"{redirect_uri}?error=authentication_failed")


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    logger.info(f"Current user request: {current_user.id} - {current_user.email}")
    return current_user


@router.post("/github/callback")
async def github_callback_post(request: dict):
    """Handle GitHub OAuth callback from frontend"""
    code = request.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code required")

    try:
        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                },
            )
            token_data = token_response.json()

            if "error" in token_data:
                raise HTTPException(
                    status_code=400, detail=token_data["error_description"]
                )

            access_token = token_data["access_token"]

            # Get user info from GitHub
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            github_user = user_response.json()

            # Get user email if not public
            if not github_user.get("email"):
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                emails = email_response.json()
                primary_email = next((e["email"] for e in emails if e["primary"]), None)
                github_user["email"] = primary_email

        # Create or update user in database
        async with get_async_session() as session:
            # Try to find existing user by github_id
            existing_user_result = await session.execute(
                select(UserModel).where(UserModel.github_id == str(github_user["id"]))
            )
            user = existing_user_result.scalar_one_or_none()
            
            if user:
                # Update existing user
                user.email = github_user.get("email")
                user.name = github_user.get("name")
                user.image = github_user.get("avatar_url")
                session.add(user)
            else:
                # Create new user
                user = UserModel(
                    email=github_user.get("email"),
                    name=github_user.get("name"),
                    github_id=str(github_user["id"]),
                    image=github_user.get("avatar_url"),
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)

            # Update or create account record
            existing_account_result = await session.execute(
                select(Account).where(
                    and_(
                        Account.provider == "github",
                        Account.provider_account_id == str(github_user["id"])
                    )
                )
            )
            account = existing_account_result.scalar_one_or_none()
            
            if account:
                # Update existing account
                account.access_token = access_token
                account.token_type = "bearer"
                account.scope = token_data.get("scope")
                session.add(account)
            else:
                # Create new account
                account = Account(
                    user_id=user.id,
                    type="oauth",
                    provider="github",
                    provider_account_id=str(github_user["id"]),
                    access_token=access_token,
                    token_type="bearer",
                    scope=token_data.get("scope"),
                )
                session.add(account)
            
            await session.commit()

        # Create JWT token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        jwt_token = create_access_token(
            data={"sub": user.id}, expires_delta=access_token_expires
        )

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "image": user.image,
                "githubId": user.github_id,
            },
        }

    except Exception as e:
        logger.error(f"GitHub OAuth error: {str(e)}")
        raise HTTPException(status_code=400, detail="Authentication failed")


@router.post("/exchange-session")
async def exchange_session(request: dict):
    """Exchange NextAuth session for JWT token"""
    session_user = request.get("sessionUser")
    access_token = request.get("accessToken")

    if not session_user or not session_user.get("email"):
        raise HTTPException(status_code=400, detail="Invalid session data")

    try:
        # Find or create user based on session data
        logger.info(f"Session exchange for user: {session_user.get('email')}")

        async with get_async_session() as session:
            # Try to find existing user by email
            existing_user_result = await session.execute(
                select(UserModel).where(UserModel.email == session_user["email"])
            )
            user = existing_user_result.scalar_one_or_none()
            
            if user:
                # Update existing user
                user.name = session_user.get("name")
                user.image = session_user.get("image")
                session.add(user)
            else:
                # Create new user
                user = UserModel(
                    email=session_user["email"],
                    name=session_user.get("name"),
                    image=session_user.get("image"),
                    github_id=None,  # Will be set if GitHub OAuth
                )
                session.add(user)
            
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"User upserted: {user.id} - {user.email}")

            # If this is from GitHub OAuth and we have an access token, store it
            if access_token:
                # Try to get GitHub user ID from the access token
                async with httpx.AsyncClient() as client:
                    try:
                        github_response = await client.get(
                            "https://api.github.com/user",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/vnd.github.v3+json",
                            },
                        )
                        if github_response.status_code == 200:
                            github_user = github_response.json()

                            # Update user with GitHub ID
                            user.github_id = str(github_user["id"])
                            session.add(user)
                            await session.commit()

                            # Store GitHub account
                            existing_account_result = await session.execute(
                                select(Account).where(
                                    and_(
                                        Account.provider == "github",
                                        Account.provider_account_id == str(github_user["id"])
                                    )
                                )
                            )
                            account = existing_account_result.scalar_one_or_none()
                            
                            if account:
                                # Update existing account
                                account.access_token = access_token
                                account.token_type = "bearer"
                                session.add(account)
                            else:
                                # Create new account
                                account = Account(
                                    user_id=user.id,
                                    type="oauth",
                                    provider="github",
                                    provider_account_id=str(github_user["id"]),
                                    access_token=access_token,
                                    token_type="bearer",
                                )
                                session.add(account)
                            
                            await session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to fetch GitHub user info: {e}")

        # Create JWT token
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        jwt_token = create_access_token(
            data={"sub": user.id}, expires_delta=access_token_expires
        )

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "image": user.image,
                "githubId": user.github_id,
            },
        }

    except Exception as e:
        logger.error(f"Session exchange error: {str(e)}")
        raise HTTPException(status_code=400, detail="Failed to exchange session")


@router.post("/logout")
async def logout():
    """Logout endpoint (handled by frontend)"""
    return {"message": "Logged out successfully"}
