from typing import Optional
import strawberry
import requests
from flask import request as flask_request


def _get_auth_header() -> dict:
    token = flask_request.headers.get("Authorization", "")
    return {"Authorization": token}


SERVICES = {
    "document": "http://document-pipeline:5001",
    "support": "http://support-services:5003",
}


@strawberry.type
class Classification:
    label_name: Optional[str] = None
    label: Optional[str] = None
    confidence: Optional[float] = None


@strawberry.type
class Entities:
    nomor_surat: Optional[str] = None
    perihal: Optional[str] = None
    organisasi_penerbit: Optional[str] = None
    pengirim: Optional[str] = None
    penerima: Optional[str] = None
    tanggal_surat: Optional[str] = None
    dates: Optional[list[str]] = None


@strawberry.type
class Delegation:
    id: str
    name: str


@strawberry.type
class GoogleDrive:
    file_id: Optional[str] = None
    web_view_link: Optional[str] = None
    web_content_link: Optional[str] = None


def _make_summary(item: dict) -> str:
    stored = item.get("summary")
    if stored:
        return str(stored)
    content = item.get("content")
    if not content:
        return "No text extracted."
    cleaned = str(content).strip()
    if len(cleaned) <= 200:
        return cleaned
    return cleaned[:200].rsplit(" ", 1)[0] + "..."


@strawberry.type
class Document:
    id: str
    title: str
    filename: str
    summary: str
    content: Optional[str] = None
    status: str
    uploaded_at: Optional[str] = None
    uploaded_by: Optional[str] = None
    uploaded_by_name: Optional[str] = None
    mimetype: Optional[str] = None
    org_id: Optional[str] = None
    classification: Optional[Classification] = None
    entities: Optional[Entities] = None
    delegation: Optional[Delegation] = None
    google_drive: Optional[GoogleDrive] = None
    security_suggestion: Optional[str] = None
    file_data: Optional[str] = None
    is_generated: Optional[bool] = None
    generator_type: Optional[str] = None
    generator_status: Optional[str] = None

    @strawberry.field
    def reminders(self) -> list["Reminder"]:
        headers = _get_auth_header()
        resp = requests.get(f"{SERVICES['support']}/reminder/", headers=headers, timeout=30)
        if resp.status_code != 200:
            return []
        items = resp.json() if isinstance(resp.json(), list) else []
        return [
            Reminder(
                id=r.get("_id", r.get("id", "")),
                task=r.get("task", ""),
                date=r.get("date", ""),
                time=r.get("time", ""),
                location=r.get("location", ""),
                doc_id=r.get("doc_id", ""),
            )
            for r in items if r.get("doc_id") == self.id
        ]


@strawberry.type
class Reminder:
    id: str
    task: str
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    doc_id: Optional[str] = None


def _parse_classification(data: dict) -> Optional[Classification]:
    if not data:
        return None
    return Classification(
        label_name=data.get("label_name"),
        label=data.get("label"),
        confidence=data.get("confidence"),
    )


def _parse_entities(data: dict) -> Optional[Entities]:
    if not data:
        return None
    raw_dates = data.get("dates")
    return Entities(
        nomor_surat=data.get("nomor_surat"),
        perihal=data.get("perihal"),
        organisasi_penerbit=data.get("organisasi_penerbit"),
        pengirim=data.get("pengirim"),
        penerima=data.get("penerima"),
        tanggal_surat=data.get("tanggal_surat"),
        dates=raw_dates if isinstance(raw_dates, list) else None,
    )


def _parse_delegation(data: dict) -> Optional[Delegation]:
    del_id = data.get("delegation_id")
    del_name = data.get("delegation_name")
    if not del_id and not del_name:
        return None
    return Delegation(id=del_id or "general", name=del_name or "General")


def _parse_google_drive(data: dict) -> Optional[GoogleDrive]:
    if not data:
        return None
    return GoogleDrive(
        file_id=data.get("file_id"),
        web_view_link=data.get("web_view_link"),
        web_content_link=data.get("web_content_link"),
    )


def _doc_from_rest(item: dict) -> Document:
    classification_data = item.get("classification") or {}
    entities_data = item.get("entities") or {}
    delegation_data = item.get("delegation") or item

    return Document(
        id=str(item.get("doc_id", "")),
        title=str(item.get("title", item.get("filename", ""))),
        filename=str(item.get("filename", "")),
        summary=_make_summary(item),
        content=str(item.get("content", "")),
        status=str(item.get("status", "processed")),
        uploaded_at=str(item.get("uploaded_at", "")),
        uploaded_by=str(item.get("uploaded_by") or ""),
        uploaded_by_name=str(item.get("uploaded_by_name") or ""),
        mimetype=str(item.get("mimetype", "")),
        org_id=str(item.get("org_id", "")),
        classification=_parse_classification(classification_data),
        entities=_parse_entities(entities_data),
        delegation=_parse_delegation(delegation_data),
        google_drive=_parse_google_drive(item.get("google_drive")),
        security_suggestion=str(item.get("security_suggestion") or ""),
        file_data=str(item.get("file_data") or ""),
        is_generated=item.get("is_generated"),
        generator_type=str(item.get("generator_type") or ""),
        generator_status=str(item.get("generator_status") or ""),
    )


@strawberry.type
class Query:
    @strawberry.field
    def documents(
        self, org_id: Optional[str] = None, delegation_id: Optional[str] = None
    ) -> list[Document]:
        headers = _get_auth_header()
        url = f"{SERVICES['document']}/document/list"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return []
        items = resp.json() if isinstance(resp.json(), list) else []
        return [_doc_from_rest(item) for item in items]

    @strawberry.field
    def document(self, id: str) -> Optional[Document]:
        headers = _get_auth_header()
        url = f"{SERVICES['document']}/document/{id}"
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None
        item = resp.json()
        return _doc_from_rest(item)


@strawberry.type
class Mutation:
    @strawberry.mutation
    def delete_document(self, id: str) -> bool:
        headers = _get_auth_header()
        resp = requests.delete(
            f"{SERVICES['document']}/document/{id}",
            headers=headers, timeout=30,
        )
        return resp.status_code == 200

    @strawberry.mutation
    def disposition_document(self, id: str, delegation_id: str) -> bool:
        headers = _get_auth_header()
        resp = requests.post(
            f"{SERVICES['document']}/document/disposition/{id}",
            json={"delegation_id": delegation_id},
            headers=headers, timeout=30,
        )
        return resp.status_code == 200


schema = strawberry.Schema(query=Query, mutation=Mutation)
