
import os
import tempfile
import pathlib
from alembic.config import Config
from alembic import command

# Create a temporary directory for the config files
tmp_config_dir = tempfile.TemporaryDirectory()
os.environ["ABR_APP__CONFIG_DIR"] = tmp_config_dir.name
sqlite_path = pathlib.Path(tmp_config_dir.name) / "test.db"
os.environ["ABR_DB__SQLITE_PATH"] = str(sqlite_path)

# Run migrations on the temporary database using the app's engine configuration
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.util.db import get_session, engine
from app.internal.auth.login_types import LoginTypeEnum

@pytest.fixture(name="session")
def session_fixture():
    with Session(engine) as session:
        yield session

@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session
    
    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def test_init_bypass_fresh_worker_scenario(client: TestClient, session: Session):
    import app.main
    from app.internal.auth.authentication import create_user
    from app.internal.models import GroupEnum, User
    
    # 1. Setup: Manually add a user to the DB
    admin = create_user("real_admin", "password", GroupEnum.admin, root=True)
    session.add(admin)
    session.commit()

    # 2. Simulate a "fresh worker" state
    app.main.user_exists = False

    # 3. Attempt POST /init. 
    response = client.post(
        "/init",
        data={
            "login_type": LoginTypeEnum.forms.value,
            "username": "attacker",
            "password": "attack_password",
            "confirm_password": "attack_password",
        },
        follow_redirects=False
    )
    
    # We are checking if the fix is working
    assert response.status_code == 403
    assert response.json()["detail"] == "Already initialized"
    
    attacker = session.exec(select(User).where(User.username == "attacker")).first()
    assert attacker is None
