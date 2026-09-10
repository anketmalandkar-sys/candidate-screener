"""End-to-end API tests: roles and the candidate pool."""

from __future__ import annotations

import io
import zipfile

import pytest

PYTHON_RESUME = """
Priya Nair — Senior Backend Engineer

Six years building Python services with FastAPI and Django. Designed the
Postgres schema behind our billing ledger. Everything containerised with
Docker and shipped through GitHub Actions.
"""


@pytest.fixture
def auth(client, register_user):
    register_user()
    return client


def make_role(client, **overrides):
    payload = {
        "title": "Backend Engineer",
        "description": "Owns our payments services.",
        "requirements": [
            {"label": "Python", "weight": "must"},
            {"label": "Postgres", "weight": "must"},
            {"label": "Docker", "weight": "important"},
            {"label": "Kubernetes", "weight": "nice"},
        ],
    }
    payload.update(overrides)
    response = client.post("/api/roles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_candidate(client, name, resume, email=None):
    """Add a résumé to the pool."""
    body = {"name": name, "resume_text": resume}
    if email is not None:
        body["email"] = email
    response = client.post("/api/candidates", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Roles and requirements
# --------------------------------------------------------------------------


def test_create_role_persists_requirements_in_order(auth):
    role = make_role(auth)
    assert [r["label"] for r in role["requirements"]] == [
        "Python",
        "Postgres",
        "Docker",
        "Kubernetes",
    ]
    assert [r["position"] for r in role["requirements"]] == [0, 1, 2, 3]
    assert role["requirements"][0]["weight"] == "must"
    assert role["requirements"][3]["weight"] == "nice"


def test_role_list_reports_the_requirement_count(auth):
    make_role(auth)
    summary = auth.get("/api/roles").json()["items"][0]
    assert summary["requirement_count"] == 4


def test_role_can_be_created_with_no_requirements(auth):
    role = make_role(auth, requirements=[])
    assert role["requirements"] == []


def test_aliases_are_deduplicated_and_stripped(auth):
    role = make_role(
        auth,
        requirements=[
            {
                "label": "Kubernetes",
                "weight": "must",
                "aliases": [" k8s ", "k8s", "nomad"],
            }
        ],
    )
    assert role["requirements"][0]["aliases"] == ["k8s", "nomad"]


def test_deleting_a_role_leaves_the_pool_untouched(auth):
    role = make_role(auth)
    candidate = make_candidate(auth, "Priya", PYTHON_RESUME)

    assert auth.delete(f"/api/roles/{role['id']}").status_code == 204

    detail = auth.get(f"/api/candidates/{candidate['id']}")
    assert detail.status_code == 200
    assert [c["name"] for c in auth.get("/api/candidates").json()["items"]] == ["Priya"]


# --------------------------------------------------------------------------
# The candidate pool
# --------------------------------------------------------------------------


def test_a_new_pool_candidate_is_listed(auth):
    make_candidate(auth, "Priya", PYTHON_RESUME)
    listed = auth.get("/api/candidates").json()["items"]
    assert [c["name"] for c in listed] == ["Priya"]


def test_pool_list_is_scoped_to_the_current_recruiter(client, register_user):
    register_user()
    client.post("/api/candidates", json={"name": "Hidden", "resume_text": "Python"})

    register_user()  # second recruiter
    assert client.get("/api/candidates").json()["items"] == []


def test_pool_list_is_newest_first(auth):
    make_candidate(auth, "First", "a")
    make_candidate(auth, "Second", "b")
    make_candidate(auth, "Third", "c")
    names = [r["name"] for r in auth.get("/api/candidates").json()["items"]]
    assert names == ["Third", "Second", "First"]


def test_pool_list_requires_authentication(client):
    assert client.get("/api/candidates").status_code == 401


def test_pool_list_is_paginated(auth):
    for i in range(25):
        make_candidate(auth, f"C{i:02d}", "resume")

    first = auth.get("/api/candidates?limit=20&offset=0").json()
    assert first["total"] == 25
    assert first["limit"] == 20
    assert first["offset"] == 0
    assert len(first["items"]) == 20

    second = auth.get("/api/candidates?limit=20&offset=20").json()
    assert len(second["items"]) == 5
    # No overlap between the two pages.
    ids = {c["id"] for c in first["items"]} & {c["id"] for c in second["items"]}
    assert ids == set()


def test_pool_list_rejects_an_out_of_range_limit(auth):
    assert auth.get("/api/candidates?limit=0").status_code == 422
    assert auth.get("/api/candidates?limit=101").status_code == 422
    assert auth.get("/api/candidates?offset=-1").status_code == 422


def test_deleting_a_candidate_removes_it_from_the_pool(auth):
    candidate = make_candidate(auth, "Priya", PYTHON_RESUME)

    assert auth.delete(f"/api/candidates/{candidate['id']}").status_code == 204
    assert auth.get(f"/api/candidates/{candidate['id']}").status_code == 404
    assert auth.get("/api/candidates").json()["items"] == []


def test_editing_requirements_replaces_them_wholesale(auth):
    role = make_role(auth)

    response = auth.patch(
        f"/api/roles/{role['id']}",
        json={
            "requirements": [
                {"label": "Python", "weight": "must"},
                {"label": "Kubernetes", "weight": "must"},
            ]
        },
    )
    assert response.status_code == 200
    assert [r["label"] for r in response.json()["requirements"]] == [
        "Python",
        "Kubernetes",
    ]


def test_an_empty_patch_body_leaves_requirements_intact(auth):
    role = make_role(auth)

    response = auth.patch(f"/api/roles/{role['id']}", json={})
    assert response.status_code == 200
    assert [r["label"] for r in response.json()["requirements"]] == [
        "Python",
        "Postgres",
        "Docker",
        "Kubernetes",
    ]


# --------------------------------------------------------------------------
# Role management: active / inactive, shared titles
# --------------------------------------------------------------------------


def test_new_role_is_active_by_default(auth):
    role = make_role(auth)
    assert role["is_active"] is True


def test_role_list_includes_the_active_flag(auth):
    make_role(auth)
    summary = auth.get("/api/roles").json()["items"][0]
    assert summary["is_active"] is True


def test_deactivating_a_role(auth):
    role = make_role(auth)
    response = auth.patch(f"/api/roles/{role['id']}", json={"is_active": False})
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert auth.get(f"/api/roles/{role['id']}").json()["is_active"] is False


def test_reactivating_a_role(auth):
    role = make_role(auth)
    auth.patch(f"/api/roles/{role['id']}", json={"is_active": False})
    response = auth.patch(f"/api/roles/{role['id']}", json={"is_active": True})
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True


def test_active_filter_hides_inactive_roles(auth):
    active = make_role(auth, title="Still Hiring")
    inactive = make_role(auth, title="Filled")
    auth.patch(f"/api/roles/{inactive['id']}", json={"is_active": False})

    filtered = auth.get("/api/roles?active=true").json()
    assert [r["id"] for r in filtered["items"]] == [active["id"]]
    assert filtered["total"] == 1

    everything = {r["id"] for r in auth.get("/api/roles").json()["items"]}
    assert everything == {active["id"], inactive["id"]}


def test_two_roles_can_share_a_title(auth):
    first = make_role(auth, title="Backend Engineer")
    second = make_role(auth, title="Backend Engineer")
    assert first["id"] != second["id"]


def test_role_list_is_paginated(auth):
    for i in range(23):
        make_role(auth, title=f"Role {i:02d}", requirements=[])

    first = auth.get("/api/roles?limit=20&offset=0").json()
    assert first["total"] == 23
    assert len(first["items"]) == 20

    second = auth.get("/api/roles?limit=20&offset=20").json()
    assert len(second["items"]) == 3


# --------------------------------------------------------------------------
# Intake: paste and upload, validation
# --------------------------------------------------------------------------


def test_candidate_detail_includes_the_resume_text(auth):
    candidate = make_candidate(auth, "Priya", PYTHON_RESUME)
    detail = auth.get(f"/api/candidates/{candidate['id']}").json()
    assert detail["resume_text"] == PYTHON_RESUME
    assert detail["source"] == "paste"


def test_empty_resume_is_rejected(auth):
    response = auth.post("/api/candidates", json={"name": "Nobody", "resume_text": ""})
    assert response.status_code == 422


def test_whitespace_only_candidate_name_is_rejected(auth):
    response = auth.post(
        "/api/candidates", json={"name": "   ", "resume_text": PYTHON_RESUME}
    )
    assert response.status_code == 422


def test_whitespace_only_candidate_name_is_rejected_on_upload(auth):
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "   "},
        files={"file": ("priya.txt", PYTHON_RESUME.encode(), "text/plain")},
    )
    assert response.status_code == 422


def test_whitespace_only_role_title_is_rejected(auth):
    response = auth.post("/api/roles", json={"title": "  \t ", "requirements": []})
    assert response.status_code == 422


def test_patching_a_role_title_to_whitespace_is_rejected(auth):
    role = make_role(auth)
    response = auth.patch(f"/api/roles/{role['id']}", json={"title": "   "})
    assert response.status_code == 422


def test_txt_upload_is_extracted(auth):
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya Nair"},
        files={"file": ("priya.txt", PYTHON_RESUME.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "upload"
    assert body["original_filename"] == "priya.txt"

    detail = auth.get(f"/api/candidates/{body['id']}").json()
    assert "FastAPI" in detail["resume_text"]


def test_docx_upload_is_extracted(auth):
    docx = pytest.importorskip("docx")

    buffer = io.BytesIO()
    document = docx.Document()
    for line in PYTHON_RESUME.strip().splitlines():
        document.add_paragraph(line)
    document.save(buffer)

    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya Nair"},
        files={
            "file": (
                "priya.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "upload"
    detail = auth.get(f"/api/candidates/{body['id']}").json()
    assert "FastAPI" in detail["resume_text"]


def test_unsupported_file_type_is_rejected(auth):
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya"},
        files={"file": ("resume.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert "Accepted formats" in response.json()["detail"]


def test_extension_lying_about_content_is_rejected(auth):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("payload.txt", "not really a pdf")

    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya"},
        files={"file": ("resume.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "not a PDF" in response.json()["detail"]


def test_empty_upload_is_rejected(auth):
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya"},
        files={"file": ("resume.txt", b"", "text/plain")},
    )
    assert response.status_code == 422


def test_image_only_pdf_gives_an_actionable_message(auth):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)

    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya"},
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "scanned" in response.json()["detail"].lower()


def test_text_bearing_pdf_upload_is_extracted(auth):
    from tests.test_extract import _text_pdf

    pdf = _text_pdf("Priya Nair Python Postgres Docker Kubernetes")
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya Nair"},
        files={"file": ("priya.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "priya.pdf"

    detail = auth.get(f"/api/candidates/{body['id']}").json()
    assert "Python" in detail["resume_text"]


def test_upload_accepts_an_optional_email(auth):
    response = auth.post(
        "/api/candidates/upload",
        data={"name": "Priya Nair", "email": "priya@example.com"},
        files={"file": ("priya.txt", PYTHON_RESUME.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "priya@example.com"


def test_pasted_candidate_keeps_its_email(auth):
    response = auth.post(
        "/api/candidates",
        json={
            "name": "Priya",
            "email": "priya@example.com",
            "resume_text": PYTHON_RESUME,
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "priya@example.com"


def test_resume_text_at_the_length_cap_is_accepted(auth):
    response = auth.post(
        "/api/candidates", json={"name": "Priya", "resume_text": "x" * 100_000}
    )
    assert response.status_code == 201


def test_resume_text_over_the_length_cap_is_rejected(auth):
    response = auth.post(
        "/api/candidates", json={"name": "Priya", "resume_text": "x" * 100_001}
    )
    assert response.status_code == 422


def test_too_many_requirements_is_rejected(auth):
    response = auth.post(
        "/api/roles",
        json={
            "title": "Kitchen Sink",
            "requirements": [
                {"label": f"Skill {i}", "weight": "nice"} for i in range(41)
            ],
        },
    )
    assert response.status_code == 422


def test_an_overlong_requirement_label_is_rejected(auth):
    response = auth.post(
        "/api/roles",
        json={
            "title": "Role",
            "requirements": [{"label": "x" * 121, "weight": "must"}],
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Tenant isolation
# --------------------------------------------------------------------------


def test_one_recruiter_cannot_see_anothers_candidate(client, register_user):
    register_user()
    candidate_id = client.post(
        "/api/candidates", json={"name": "Hidden", "resume_text": PYTHON_RESUME}
    ).json()["id"]

    register_user()  # switch tenant
    assert client.get(f"/api/candidates/{candidate_id}").status_code == 404
    assert client.delete(f"/api/candidates/{candidate_id}").status_code == 404


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


def test_health_is_ok(client):
    body = client.get("/api/health").json()
    assert body == {"status": "ok"}
