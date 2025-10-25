from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from .extensions import db
from .models import Document, DocumentVersion, SearchIndex
from .utils import allowed_file, read_text_file

bp = Blueprint("documents", __name__)


@bp.app_template_filter("datetimeformat")
def datetimeformat(value, fmt: str = "%d.%m.%Y %H:%M") -> str:
    if value is None:
        return ""
    return value.strftime(fmt)


def require_editor() -> None:
    if not current_user.is_authenticated or not current_user.is_editor:
        abort(403)


@bp.route("/")
@login_required
def dashboard():
    documents = Document.query.order_by(Document.updated_at.desc(), Document.created_at.desc()).all()
    return render_template("documents/dashboard.html", documents=documents)


@bp.route("/documents/<slug>")
@login_required
def detail(slug: str):
    document = Document.query.filter_by(slug=slug).first_or_404()
    return render_template("documents/detail.html", document=document)


@bp.route("/documents/create", methods=["GET", "POST"])
@login_required
def create():
    require_editor()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        file = request.files.get("file")

        if not title:
            flash("Название документа обязательно", "danger")
            return render_template("documents/create.html")

        document = Document(title=title, summary=summary, owner=current_user)
        db.session.add(document)
        db.session.flush()

        document.ensure_slug()

        filename: Optional[str] = None
        file_path: Optional[str] = None
        if file and file.filename:
            filename = file.filename
            if allowed_file(filename):
                upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
                upload_folder.mkdir(exist_ok=True, parents=True)
                safe_name = f"{document.id}_{int(datetime.utcnow().timestamp())}_{filename}"
                destination = upload_folder / safe_name
                file.save(destination)
                file_path = str(destination)
                if not content:
                    content = read_text_file(destination)
            else:
                flash("Поддерживаются только текстовые файлы .txt и .md", "warning")

        if not content:
            flash("Необходимо заполнить содержимое документа или загрузить файл", "danger")
            db.session.rollback()
            return render_template("documents/create.html")

        version = DocumentVersion(
            document=document,
            version_number=1,
            filename=filename,
            file_path=file_path,
            content=content,
            editor=current_user,
        )
        db.session.add(version)
        db.session.flush()

        document.current_version = version
        SearchIndex.rebuild_for_document(document)
        db.session.commit()

        flash("Документ успешно создан", "success")
        return redirect(url_for("documents.detail", slug=document.slug))

    return render_template("documents/create.html")


@bp.route("/documents/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit(slug: str):
    require_editor()
    document = Document.query.filter_by(slug=slug).first_or_404()
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        summary = request.form.get("summary", "").strip()
        comment = request.form.get("comment", "").strip()
        if not content:
            flash("Содержимое не может быть пустым", "danger")
        else:
            version_number = (document.current_version.version_number + 1) if document.current_version else 1
            version = DocumentVersion(
                document=document,
                version_number=version_number,
                content=content,
                editor=current_user,
                comment=comment or "Обновлено",
                filename=document.current_version.filename if document.current_version else None,
                file_path=document.current_version.file_path if document.current_version else None,
            )
            document.summary = summary
            document.current_version = version
            document.updated_at = datetime.utcnow()
            db.session.add(version)
            SearchIndex.rebuild_for_document(document)
            db.session.commit()
            flash("Документ обновлен", "success")
            return redirect(url_for("documents.detail", slug=document.slug))
    return render_template("documents/edit.html", document=document)


@bp.route("/documents/<slug>/history")
@login_required
def history(slug: str):
    document = Document.query.filter_by(slug=slug).first_or_404()
    return render_template("documents/history.html", document=document)


@bp.route("/documents/<slug>/download")
@login_required
def download(slug: str):
    document = Document.query.filter_by(slug=slug).first_or_404()
    version = document.current_version
    if not version or not version.file_path:
        abort(404)
    path = Path(version.file_path)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=version.filename or f"{document.slug}.txt")
