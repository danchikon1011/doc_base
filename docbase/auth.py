from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import Role, User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("documents.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash("Добро пожаловать назад!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("documents.dashboard"))
        flash("Неверное имя пользователя или пароль", "danger")
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if not current_user.is_admin:
        flash("У вас нет прав для создания новых пользователей", "warning")
        return redirect(url_for("documents.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role_name = request.form.get("role", Role.VIEWER.value)
        if not username or not password:
            flash("Имя пользователя и пароль обязательны", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Пользователь с таким именем уже существует", "danger")
        else:
            role = Role(role_name)
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Пользователь успешно создан", "success")
            return redirect(url_for("auth.login"))
    role_labels = {
        Role.ADMIN: "Администратор",
        Role.EDITOR: "Редактор",
        Role.VIEWER: "Наблюдатель",
    }
    return render_template("auth/register.html", roles=Role, role_labels=role_labels)
