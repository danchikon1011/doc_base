"""Helper script to create initial roles and an admin user."""
import argparse

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.models import Department, Role, User


def main(email: str, password: str, full_name: str):
    with SessionLocal() as session:
        admin_role = session.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            admin_role = Role(name="admin", description="Администратор")
            session.add(admin_role)
        employee_role = session.query(Role).filter(Role.name == "employee").first()
        if not employee_role:
            employee_role = Role(name="employee", description="Сотрудник")
            session.add(employee_role)

        department = session.query(Department).first()
        if not department:
            department = Department(name="Общий отдел", description="Отдел по умолчанию")
            session.add(department)
            session.flush()

        user = session.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                full_name=full_name,
                hashed_password=get_password_hash(password),
                department_id=department.id,
                is_active=True,
            )
            session.add(user)
            session.flush()

        if admin_role not in user.roles:
            user.roles.append(admin_role)
        if employee_role not in user.roles:
            user.roles.append(employee_role)

        session.commit()
        print(f"Admin user ready: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Создание администратора DocuFlow")
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument("full_name")
    args = parser.parse_args()
    main(args.email, args.password, args.full_name)
