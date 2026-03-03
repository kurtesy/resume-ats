"""Application dependencies."""

from fastapi import Header, HTTPException

from app.database import Database


def get_db(x_username: str | None = Header(None)) -> Database:
    """Get a database instance for the user specified in the X-Username header."""
    print(x_username)
    if not x_username:
        x_username = "nishant"
        # raise HTTPException(
        #     status_code=400,
        #     detail="X-Username header is required for multi-user mode.",
        # )
    # In a real-world app, you'd validate the user from a session/token.
    # For this implementation, we trust the header.
    return Database(username=x_username)
