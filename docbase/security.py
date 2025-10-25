from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Protocol

from flask import current_app, flash, g, redirect, request, session, url_for
from werkzeug.local import LocalProxy


class SupportsGetID(Protocol):
    def get_id(self) -> str | None:  # pragma: no cover - protocol definition
        ...


class UserMixin:
    """Lightweight replacement for Flask-Login's UserMixin."""

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(getattr(self, "id"))


class AnonymousUser(UserMixin):
    @property
    def is_authenticated(self) -> bool:  # pragma: no cover - simple property
        return False

    @property
    def is_active(self) -> bool:  # pragma: no cover - simple property
        return False

    @property
    def is_anonymous(self) -> bool:  # pragma: no cover - simple property
        return True

    def get_id(self) -> None:  # pragma: no cover - simple property
        return None


class AuthManager:
    """Minimal session-based authentication manager."""

    def __init__(self) -> None:
        self.login_view = "auth.login"
        self.login_message = "Пожалуйста, войдите в систему."
        self.login_message_category = "warning"
        self.anonymous_user_class = AnonymousUser
        self._user_loader: Optional[Callable[[str], Optional[SupportsGetID]]] = None

    # Lifecycle -----------------------------------------------------------------
    def init_app(self, app) -> None:
        @app.before_request
        def load_current_user() -> None:
            g._current_user = self._load_user_from_session()

        @app.context_processor
        def inject_user() -> dict[str, LocalProxy]:
            return {"current_user": current_user}

    # Registration --------------------------------------------------------------
    def user_loader(self, callback: Callable[[str], Optional[SupportsGetID]]):
        self._user_loader = callback
        return callback

    # Helpers -------------------------------------------------------------------
    def _anonymous_user(self) -> AnonymousUser:
        return self.anonymous_user_class()

    def _get_current_user(self) -> SupportsGetID:
        return getattr(g, "_current_user", None) or self._anonymous_user()

    def _set_current_user(self, user: SupportsGetID) -> None:
        g._current_user = user

    def _load_user_from_session(self) -> SupportsGetID:
        if self._user_loader is None:
            return self._anonymous_user()
        user_id = session.get("user_id")
        if user_id is None:
            return self._anonymous_user()
        user = self._user_loader(str(user_id))
        return user or self._anonymous_user()

    # Public API ----------------------------------------------------------------
    def login_user(self, user: SupportsGetID, remember: bool = False) -> None:
        session["user_id"] = user.get_id()
        session.permanent = bool(remember)
        self._set_current_user(user)

    def logout_user(self) -> None:
        session.pop("user_id", None)
        self._set_current_user(self._anonymous_user())

    def login_required(self, view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            current = self._get_current_user()
            if not getattr(current, "is_authenticated", False):
                if self.login_message:
                    flash(self.login_message, self.login_message_category)
                target = self.login_view or "auth.login"
                return redirect(url_for(target, next=request.url))
            return view_func(*args, **kwargs)

        return wrapped_view

def _get_manager(app=None) -> AuthManager:
    app = app or current_app
    manager = app.extensions.get("auth_manager")
    if manager is None:
        manager = AuthManager()
        manager.init_app(app)
        app.extensions["auth_manager"] = manager
    return manager


def init_auth_manager(app) -> AuthManager:
    return _get_manager(app)


current_user = LocalProxy(lambda: _get_manager()._get_current_user())


def login_user(user: SupportsGetID, remember: bool = False) -> None:
    manager = _get_manager()
    manager.login_user(user, remember=remember)


def logout_user() -> None:
    manager = _get_manager()
    manager.logout_user()


def login_required(view_func):
    manager = _get_manager()
    return manager.login_required(view_func)
