import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).parent))

from app.config import Paths  # noqa: E402
from app.main import build_services, create_app  # noqa: E402
from app.services.embeddings import TfidfLsaEmbedder  # noqa: E402
from app.services.managers import ModelManager  # noqa: E402
from helpers import StubNLI  # noqa: E402

REPO = BACKEND.parent
SAMPLES = REPO / "data" / "samples"


@pytest.fixture()
def paths(tmp_path):
    p = Paths.from_dirs(root=tmp_path, data=tmp_path / "data", reports=tmp_path / "reports")
    p.samples = SAMPLES          # use the real sample files
    p.ensure()
    return p


@pytest.fixture()
def client(paths):
    """App with stub NLI + TF-IDF/LSA dense retrieval (no network, no model weights)."""
    from app.database import Database
    from app.services.managers import SettingsStore

    db = Database(paths.db)
    settings = SettingsStore(db)
    models = ModelManager(settings, nli_factory=lambda s: StubNLI(), embedder_factory=lambda s: TfidfLsaEmbedder())
    models.load_all()
    app = create_app(paths=paths, models=models, load_models=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def loaded_client(client):
    r = client.post("/api/samples/load")
    assert r.status_code == 200 and r.json()["loaded"]
    client.post("/api/documents/rebuild-index?wait=true")
    return client
