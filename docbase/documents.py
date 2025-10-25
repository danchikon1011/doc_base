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

from .extensions import db
from .models import (
    ApprovalDecision,
    ApprovalState,
    Document,
    DocumentApproval,
    DocumentVersion,
    Role,
    SearchIndex,
    User,
)
from .security import current_user, login_required
from .utils import (
    EDITABLE_EXTENSIONS,
    allowed_file,
    detect_mime_type,
    ensure_directory,
    extract_text_from_file,
    write_content_to_file,
)

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
        file_extension: Optional[str] = None
        mime_type: Optional[str] = None
        file_size: Optional[int] = None
        if file and file.filename:
            filename = file.filename
            if allowed_file(filename):
                upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
                ensure_directory(upload_folder)
                file_extension = filename.rsplit(".", 1)[1].lower()
                safe_name = f"{document.id}_{int(datetime.utcnow().timestamp())}_{filename}"
                destination = upload_folder / safe_name
                file.save(destination)
                file_path = str(destination)
                mime_type = detect_mime_type(filename)
                file_size = destination.stat().st_size
                if not content:
                    try:
                        content = extract_text_from_file(destination, file_extension)
                    except Exception as exc:  # pragma: no cover - defensive
                        current_app.logger.exception("Не удалось извлечь текст", exc_info=exc)
                        content = ""
            else:
                flash("Этот формат файла не поддерживается", "warning")

        if not content and filename:
            content = f"Содержимое файла {filename} недоступно для предварительного просмотра, но документ сохранен в системе."

        if not content:
            flash("Необходимо заполнить содержимое документа или загрузить файл", "danger")
            db.session.rollback()
            return render_template("documents/create.html")

        version = DocumentVersion(
            document=document,
            version_number=1,
            filename=filename,
            file_path=file_path,
            file_extension=file_extension,
            mime_type=mime_type,
            file_size=file_size,
            content=content,
            editor=current_user,
            comment="Создан документ",
        )
        db.session.add(version)
        db.session.flush()

        document.current_version = version
        document.summary = summary
        document.approval_state = ApprovalState.DRAFT
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
        current_version = document.current_version
        if current_version and not current_version.is_editable:
            flash("Редактирование недоступно для данного типа файла", "warning")
            return redirect(url_for("documents.detail", slug=document.slug))

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
                file_extension=document.current_version.file_extension if document.current_version else None,
                mime_type=document.current_version.mime_type if document.current_version else None,
                file_size=document.current_version.file_size if document.current_version else None,
            )
            if version.file_extension in EDITABLE_EXTENSIONS and version.file_path:
                try:
                    destination = Path(version.file_path)
                    write_content_to_file(content, version.file_extension or "txt", destination)
                    version.file_size = destination.stat().st_size
                except Exception as exc:  # pragma: no cover - defensive
                    current_app.logger.exception("Не удалось обновить файл", exc_info=exc)

            document.summary = summary
            document.current_version = version
            document.updated_at = datetime.utcnow()
            document.reset_approvals()
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


@bp.route("/documents/<slug>/print")
@login_required
def print_view(slug: str):
    document = Document.query.filter_by(slug=slug).first_or_404()
    version = document.current_version
    if not version:
        abort(404)
    return render_template("documents/print.html", document=document, version=version)


@bp.route("/documents/<slug>/approvals", methods=["POST"])
@login_required
def request_approval(slug: str):
    require_editor()
    document = Document.query.filter_by(slug=slug).first_or_404()
    assigned_to_id = request.form.get("assignee")
    comment = request.form.get("comment", "").strip() or None
    if not assigned_to_id:
        flash("Выберите пользователя для согласования", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    user = User.query.get(int(assigned_to_id))
    if not user:
        flash("Пользователь не найден", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    if user.id == current_user.id and not current_user.is_admin:
        flash("Нельзя назначить согласование на себя", "warning")
        return redirect(url_for("documents.detail", slug=document.slug))

    existing = DocumentApproval.query.filter_by(
        document_id=document.id,
        assigned_to_id=user.id,
        status=ApprovalDecision.PENDING,
    ).first()
    if existing:
        flash("Для этого пользователя уже есть активный запрос", "warning")
        return redirect(url_for("documents.detail", slug=document.slug))

    approval = DocumentApproval(
        document=document,
        requested_by=current_user,
        assigned_to=user,
        comment=comment,
    )
    document.approval_state = ApprovalState.PENDING
    db.session.add(approval)
    db.session.commit()

    flash("Запрос на согласование отправлен", "success")
    return redirect(url_for("documents.detail", slug=document.slug))


@bp.route("/documents/approvals/<int:approval_id>/decision", methods=["POST"])
@login_required
def approval_decision(approval_id: int):
    approval = DocumentApproval.query.get_or_404(approval_id)
    document = approval.document
    if not (current_user.is_admin or approval.assigned_to_id == current_user.id):
        abort(403)

    if approval.status != ApprovalDecision.PENDING:
        flash("Этот запрос уже обработан", "info")
        return redirect(url_for("documents.detail", slug=document.slug))

    decision = request.form.get("decision")
    note = request.form.get("note", "").strip() or None
    if decision == "approve":
        approval.approve(note)
        flash("Документ согласован", "success")
    elif decision == "reject":
        approval.reject(note)
        document.approval_state = ApprovalState.REJECTED
        for pending in document.approvals:
            if pending.id != approval.id and pending.status == ApprovalDecision.PENDING:
                pending.cancel(reason="Документ отклонен другим пользователем")
        flash("Документ отклонен", "danger")
    else:
        flash("Неизвестное действие", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    if decision == "approve":
        remaining = [a for a in document.approvals if a.status == ApprovalDecision.PENDING]
        if not remaining:
            document.approval_state = ApprovalState.APPROVED

    db.session.commit()
    return redirect(url_for("documents.detail", slug=document.slug))


@bp.context_processor
def inject_reviewers():
    reviewers = User.query.filter(User.role.in_([Role.ADMIN, Role.EDITOR])).order_by(User.username.asc()).all()
    return {"available_reviewers": reviewers}
