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

from .models import (
    ApprovalDecision,
    ApprovalState,
    Document,
    DocumentApproval,
    User,
)
from .security import current_user, login_required
from .utils import (
    allowed_file,
    detect_mime_type,
    ensure_directory,
    extract_text_from_file,
    prepare_preview,
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


def _get_document_or_404(slug: str) -> Document:
    document = Document.get_by_slug(slug)
    if document is None:
        abort(404)
    return document.attach_related()


@bp.route("/")
@login_required
def dashboard():
    documents = Document.list_all()
    return render_template("documents/dashboard.html", documents=documents)


@bp.route("/documents/<slug>")
@login_required
def detail(slug: str):
    document = _get_document_or_404(slug)
    return render_template("documents/detail.html", document=document)


@bp.route("/documents/create", methods=["GET", "POST"])
@login_required
def create():
    require_editor()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        summary = request.form.get("summary", "").strip() or None
        content = ""
        uploaded = request.files.get("file")

        if not title:
            flash("Название документа обязательно", "danger")
            return render_template("documents/create.html")

        filename: Optional[str] = None
        file_path: Optional[str] = None
        file_extension: Optional[str] = None
        mime_type: Optional[str] = None
        file_size: Optional[int] = None

        if uploaded and uploaded.filename:
            filename = uploaded.filename
            if allowed_file(filename):
                upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
                ensure_directory(upload_folder)
                file_extension = filename.rsplit(".", 1)[1].lower()
                safe_name = f"{int(datetime.utcnow().timestamp())}_{current_user.id}_{filename}"
                destination = upload_folder / safe_name
                uploaded.save(destination)
                file_path = str(destination)
                mime_type = detect_mime_type(filename)
                file_size = destination.stat().st_size
                if not content:
                    try:
                        content = extract_text_from_file(destination, file_extension)
                    except Exception as exc:  # pragma: no cover - defensive logging
                        current_app.logger.exception("Не удалось извлечь текст", exc_info=exc)
                        content = ""
            else:
                flash("Этот формат файла не поддерживается", "warning")

        if not content and filename:
            content = (
                f"Содержимое файла {filename} недоступно для предварительного просмотра,"
                " но документ сохранен в системе."
            )

        if not content:
            content = "Документ создан. Загрузите файл с содержимым в новой версии."

        document = Document.create(
            title=title,
            summary=summary,
            owner=current_user,
            content=content,
            version_comment="Создан документ",
            filename=filename,
            file_path=file_path,
            file_extension=file_extension,
            mime_type=mime_type,
            file_size=file_size,
        )

        flash("Документ успешно создан", "success")
        return redirect(url_for("documents.detail", slug=document.slug))

    return render_template("documents/create.html")


@bp.route("/documents/<slug>/versions", methods=["POST"])
@login_required
def upload_version(slug: str):
    require_editor()
    document = _get_document_or_404(slug)

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Выберите файл для загрузки", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    filename = uploaded.filename
    if not allowed_file(filename):
        flash("Этот формат файла не поддерживается", "warning")
        return redirect(url_for("documents.detail", slug=document.slug))

    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    ensure_directory(upload_folder)

    file_extension = filename.rsplit(".", 1)[1].lower()
    safe_name = f"{int(datetime.utcnow().timestamp())}_{current_user.id}_{filename}"
    destination = upload_folder / safe_name
    uploaded.save(destination)

    mime_type = detect_mime_type(filename)
    file_size = destination.stat().st_size

    try:
        content = extract_text_from_file(destination, file_extension)
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("Не удалось извлечь текст", exc_info=exc)
        content = ""

    if not content:
        content = (
            "Содержимое новой версии не может быть отображено, но файл сохранён в системе."
        )

    summary = request.form.get("summary", "").strip() or document.summary
    comment = request.form.get("comment", "").strip() or "Загружена новая версия"

    document.add_version(
        editor=current_user,
        content=content,
        comment=comment,
        summary=summary,
        filename=filename,
        file_path=str(destination),
        file_extension=file_extension,
        mime_type=mime_type,
        file_size=file_size,
    )

    flash("Новая версия успешно добавлена", "success")
    return redirect(url_for("documents.detail", slug=document.slug))


@bp.route("/documents/<slug>/preview")
@login_required
def preview(slug: str):
    document = _get_document_or_404(slug)
    version = document.current_version
    if not version:
        abort(404)

    preview_data = prepare_preview(
        version.file_extension,
        version.file_path,
        version.content,
    )

    return render_template(
        "documents/preview.html",
        document=document,
        version=version,
        preview=preview_data,
    )


@bp.route("/documents/<slug>/history")
@login_required
def history(slug: str):
    document = _get_document_or_404(slug)
    return render_template("documents/history.html", document=document)


@bp.route("/documents/<slug>/download")
@login_required
def download(slug: str):
    document = _get_document_or_404(slug)
    version = document.current_version
    if not version or not version.file_path:
        abort(404)
    path = Path(version.file_path)
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=version.filename or f"{document.slug}.txt")


@bp.route("/documents/<slug>/file")
@login_required
def serve_file(slug: str):
    document = _get_document_or_404(slug)
    version = document.current_version
    if not version or not version.file_path:
        abort(404)
    path = Path(version.file_path)
    if not path.exists():
        abort(404)
    mimetype = version.mime_type or detect_mime_type(version.filename or path.name)
    download_name = version.filename or path.name
    return send_file(path, mimetype=mimetype, as_attachment=False, download_name=download_name)


@bp.route("/documents/<slug>/print")
@login_required
def print_view(slug: str):
    document = _get_document_or_404(slug)
    version = document.current_version
    if not version:
        abort(404)
    return render_template("documents/print.html", document=document, version=version)


@bp.route("/documents/<slug>/approvals", methods=["POST"])
@login_required
def request_approval(slug: str):
    require_editor()
    document = _get_document_or_404(slug)
    assigned_to_id = request.form.get("assignee")
    comment = request.form.get("comment", "").strip() or None

    if not assigned_to_id:
        flash("Выберите пользователя для согласования", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    user = User.get(int(assigned_to_id))
    if not user:
        flash("Пользователь не найден", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    if user.id == current_user.id and not current_user.is_admin:
        flash("Нельзя назначить согласование на себя", "warning")
        return redirect(url_for("documents.detail", slug=document.slug))

    if any(
        approval.assigned_to_id == user.id and approval.status == ApprovalDecision.PENDING
        for approval in document.approvals
    ):
        flash("Для этого пользователя уже есть активный запрос", "warning")
        return redirect(url_for("documents.detail", slug=document.slug))

    DocumentApproval.create(
        document_id=document.id,
        requested_by=current_user,
        assigned_to=user,
        comment=comment,
    )
    document.set_approval_state(ApprovalState.PENDING)

    flash("Запрос на согласование отправлен", "success")
    return redirect(url_for("documents.detail", slug=document.slug))


@bp.route("/documents/approvals/<int:approval_id>/decision", methods=["POST"])
@login_required
def approval_decision(approval_id: int):
    approval = DocumentApproval.get(approval_id)
    if not approval:
        abort(404)

    document = Document.get(approval.document_id)
    if document is None:
        abort(404)
    document.attach_related()

    if not (current_user.is_admin or approval.assigned_to_id == current_user.id):
        abort(403)

    if approval.status != ApprovalDecision.PENDING:
        flash("Этот запрос уже обработан", "info")
        return redirect(url_for("documents.detail", slug=document.slug))

    decision = request.form.get("decision")
    note = request.form.get("note", "").strip() or None

    if decision == "approve":
        approval.approve(note)
        approvals = DocumentApproval.list_for_document(document.id)
        if all(item.status != ApprovalDecision.PENDING for item in approvals):
            document.set_approval_state(ApprovalState.APPROVED)
        flash("Документ согласован", "success")
    elif decision == "reject":
        approval.reject(note)
        document.set_approval_state(ApprovalState.REJECTED)
        for pending in DocumentApproval.list_for_document(document.id):
            if pending.id != approval.id and pending.status == ApprovalDecision.PENDING:
                pending.cancel(reason="Документ отклонен другим пользователем")
        flash("Документ отклонен", "danger")
    else:
        flash("Неизвестное действие", "danger")
        return redirect(url_for("documents.detail", slug=document.slug))

    return redirect(url_for("documents.detail", slug=document.slug))


@bp.context_processor
def inject_reviewers():
    reviewers = User.list_editors()
    return {"available_reviewers": reviewers}
